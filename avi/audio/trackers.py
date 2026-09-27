"""Rastreadores adaptativos por instrumento (docs/PLAN_MVP.md, seccion 4).

Cada rastreador tiene una *huella espectral* (plantilla sobre los bins de la FFT) que
vive dentro de su rango de busqueda. En cada frame:

1. Mascara suave: la energia de cada bin se reparte entre los rastreadores en
   proporcion a huella x activacion (NMF de un frame con plantillas conocidas, tipo
   Wiener). Los `transient` reparten la parte percusiva; `tonal`/`sustained` la armonica.
   Un componente "resto" se queda con lo que ningun rastreador busca.
2. Huella: se actualiza con lo que el rastreador capturo (en sus golpes si es
   transitorio, en frames estables si es tonal), con constante de tiempo de 2-8 s, un
   limite de cuanto se mueve el centro por segundo y un tiron suave hacia el nominal.
3. Confianza: fraccion de la energia de su rango de busqueda que se lleva. Si cae bajo
   `min_confidence`, el rango reportado vuelve al nominal y la huella se relaja al prior.
"""
from __future__ import annotations

import numpy as np

from .config import AnalyzerConfig, TrackerSpec

EPS = 1e-12


def _prior_template(freqs: np.ndarray, spec: TrackerSpec) -> np.ndarray:
    """1 dentro del rango nominal, colas gaussianas (en octavas) hasta el de busqueda."""
    lo, hi = spec.nominal_hz
    slo, shi = spec.search_hz
    f = np.maximum(freqs, 1.0)
    oct_out = np.where(f < lo, np.log2(lo / f), np.where(f > hi, np.log2(f / hi), 0.0))
    t = np.exp(-0.5 * (oct_out / 0.35) ** 2) + 0.02
    t *= (freqs >= slo) & (freqs <= shi)
    s = t.sum()
    if s <= 0:  # rango sin bins (FFT muy corta): usa el bin mas cercano al centro
        t = np.zeros_like(freqs)
        t[np.argmin(np.abs(freqs - np.sqrt(lo * hi)))] = 1.0
        return t
    return t / s


def _mass_range(template: np.ndarray, freqs: np.ndarray, lo_q=0.1, hi_q=0.9) -> tuple[float, float]:
    c = np.cumsum(template)
    c /= c[-1] + EPS
    return float(freqs[np.searchsorted(c, lo_q)]), float(freqs[min(np.searchsorted(c, hi_q), len(freqs) - 1)])


class TrackerBank:
    def __init__(self, cfg: AnalyzerConfig, freqs: np.ndarray, frame_rate: float):
        self.cfg = cfg
        self.specs = list(cfg.trackers)
        self.freqs = freqs
        self.frame_rate = frame_rate
        self.log_f = np.log2(np.maximum(freqs, 1.0))
        K = len(self.specs)

        self.window = np.stack([(freqs >= s.search_hz[0]) & (freqs <= s.search_hz[1]) for s in self.specs]).astype(float)
        self.prior = np.stack([_prior_template(freqs, s) for s in self.specs])
        self.W = self.prior.copy()
        self.transient = np.array([s.transient for s in self.specs])

        # Grupos para la mascara: percusivo (transitorios) y armonico (el resto).
        self.groups = []
        for is_tr in (True, False):
            idx = np.flatnonzero(self.transient == is_tr)
            if len(idx) == 0:
                continue
            covered = self.window[idx].max(axis=0) > 0
            resid = (~covered).astype(float)
            resid = resid / resid.sum() if resid.sum() > 0 else None
            self.groups.append({"idx": idx, "resid": resid, "h": np.zeros(len(idx) + (resid is not None))})

        hop_s = 1.0 / frame_rate
        self.alpha = hop_s / cfg.template_time_constant_s
        self.pull = hop_s / cfg.prior_pull_s
        self.relax = hop_s / 1.0
        self.conf_a = hop_s / 1.0
        search_oct = np.array([np.log2(s.search_hz[1] / s.search_hz[0]) for s in self.specs])
        self.max_shift = cfg.center_max_shift_per_s * search_oct * hop_s  # octavas por frame

        self.silence_amp = 10 ** (cfg.silence_db / 20)
        self.confidence = np.zeros(K)
        self._num = np.zeros(K)
        self._den = np.zeros(K)
        self._act = np.zeros(K)
        self.hz = [tuple(s.nominal_hz) for s in self.specs]
        self._prev_M = np.zeros((K, len(freqs)))

    # ------------------------------------------------------------------ mascara
    def separate(self, perc: np.ndarray, harm: np.ndarray) -> np.ndarray:
        """Devuelve M (K, bins): magnitud que le toca a cada rastreador en este frame."""
        M = np.zeros((len(self.specs), len(self.freqs)))
        for g in self.groups:
            X = perc if self.transient[g["idx"][0]] else harm
            total = X.sum()
            if total <= EPS:
                g["h"][:] = 0
                continue
            W = self.W[g["idx"]]
            if g["resid"] is not None:
                W = np.vstack([W, g["resid"]])
            h = np.maximum(g["h"], 1e-3 * total / len(W))
            for _ in range(self.cfg.nmf_iterations):
                V = h @ W + EPS
                h *= W @ (X / V)
            g["h"] = h
            V = h @ W + EPS
            M[g["idx"]] = (h[: len(g["idx"]), None] * W[: len(g["idx"])]) / V * X
        return M

    # --------------------------------------------------------------- adaptacion
    def adapt(self, M: np.ndarray, perc: np.ndarray, harm: np.ndarray, onsets: np.ndarray, silent: bool) -> None:
        """Actualiza huellas, confianza y rango reportado despues de separar un frame."""
        # Energia que cada rastreador podria haberse llevado: su parte (percusiva o
        # armonica) dentro de su rango de busqueda.
        avail = np.where(self.transient, self.window @ perc, self.window @ harm)
        got = M.sum(axis=1)
        full = np.sqrt(self.window @ ((perc + harm) ** 2))
        active = 0.0 if silent else (full > self.silence_amp).astype(float)
        a = self.conf_a
        self._num += a * (got - self._num)
        self._den += a * (avail - self._den)
        self._act += a * (active - self._act)
        share = got / (avail + EPS)
        self.confidence = np.clip(2.0 * self._num / (self._den + EPS), 0.0, 1.0) * self._act

        for k, spec in enumerate(self.specs):
            low_conf = self.confidence[k] < self.cfg.min_confidence
            if not silent:
                if spec.transient:
                    target = np.maximum(M[k] - self._prev_M[k], 0.0) if onsets[k] else None
                    rate = min(0.2, self.alpha * 20)  # los golpes son escasos: aprende mas por golpe
                else:
                    stable = share[k] > 0.2 and not onsets.any()
                    target = M[k] if stable else None
                    rate = self.alpha
                if target is not None:
                    target = target * self.window[k]
                    if target.sum() > EPS:
                        self._blend(k, target / target.sum(), rate)
            pull = self.relax if low_conf else self.pull
            self.W[k] = (1 - pull) * self.W[k] + pull * self.prior[k]
            self.W[k] /= self.W[k].sum() + EPS
            self._update_range(k, low_conf)
        self._prev_M = M

    def _blend(self, k: int, target: np.ndarray, rate: float) -> None:
        old_c = self.W[k] @ self.log_f
        new = (1 - rate) * self.W[k] + rate * target
        shift = abs(new @ self.log_f - old_c)
        if shift > self.max_shift[k]:  # limite de velocidad del centro
            rate *= self.max_shift[k] / shift
            new = (1 - rate) * self.W[k] + rate * target
        self.W[k] = new / (new.sum() + EPS)

    def _update_range(self, k: int, low_conf: bool) -> None:
        spec = self.specs[k]
        if low_conf:
            self.hz[k] = tuple(spec.nominal_hz)
            return
        lo, hi = _mass_range(self.W[k], self.freqs)
        lo = max(lo, spec.search_hz[0])
        hi = min(hi, spec.search_hz[1])
        olo, ohi = self.hz[k]
        h = np.log1p(self.cfg.hysteresis)
        if abs(np.log(lo / olo)) > h or abs(np.log(hi / ohi)) > h:
            self.hz[k] = (lo, hi)
