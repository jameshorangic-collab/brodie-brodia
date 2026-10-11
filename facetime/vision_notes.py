"""Caller-video proof and ONE visible signal for Brodia (P08 + P09): is the caller facing the camera, turned away, or out of frame.

Why one signal: Brodie's vision path is a ~1 fps scene reader, so anything finer (gaze percentages, micro-expressions, mood,
attraction) would be invented. Body/face orientation toward the camera is coarse, low frequency and checkable by anyone who
watches the same video, so it is the one thing we report. When the pose is unclear we ABSTAIN instead of guessing.

What it does, per job (started by the worker with --vision-notes, see facetime/worker.py):
  - samples the worker's newest received frame (job.latest, the same RGB24 frames the vision tee sends to the model) at
    --vision-notes-fps (default 1);
  - P08 frame proof: a 32x18 grey thumbnail per sample, mean absolute difference against the previous sample; the counters
    (samples, new frames, changed frames) go to stdout every 10 samples and into summary(). A stream that never changes, or a
    frame sequence that stops advancing, shows up here, not as a confident note;
  - P09 observation: MediaPipe pose (lite) on the sample -> classify() -> a label (facing_camera | turned_away | out_of_frame |
    unknown). A label becomes a note only once it holds for STABLE_N of the last WINDOW_N samples; one note per change. Notes are
    emitted as events of type vision_note (job.emit: the JSONL log, job.events, the handlers' on_event) and kept in memory;
  - camera denied / audio-only call: no frame within NO_VIDEO_S of the caller binding -> one vision_note with
    source_verified false and summary() says visual evaluation is unavailable.

Nothing is stored but text: no frames, thumbnails or landmarks are written anywhere.

VisionNote fields (the shared contract in ivyhacks-brain ops/three-agent-sprint.md):
  observed_at               seconds on the job clock (the same clock as the events' t), when the state first appeared
  source_verified           True only when derived from real received caller frames
  observable_description    a plain phrase, e.g. "turned away from the camera"
  certainty                 "clear" | "uncertain"
  optional_nearby_utterance filled by attach_utterances() from the caller transcript, else None
  (+ signal, frame_seq, samples: for debugging)

Offline check (no LiveKit; a webcam or a video file; prints the notes):
  .venv/bin/python -m facetime.vision_notes --camera 0
  .venv/bin/python -m facetime.vision_notes --video some_clip.mp4
"""
import argparse, asyncio, collections, dataclasses, os, sys, time
import numpy as np

# MediaPipe pose landmark indices
NOSE, L_EYE, R_EYE, L_EAR, R_EAR, L_SH, R_SH = 0, 2, 5, 7, 8, 11, 12

VIS_MIN = 0.6           # a landmark counts as visible above this MediaPipe visibility
# Head yaw (primary): |nose x - ear midpoint x| / half the ear distance. Measured with pose lite on 2026-10-10: a frontal portrait
# 0.00 (0.14 mirrored), a head in full profile 1.58 (2.37 mirrored). Between the bands we abstain.
FACING_MAX_YAW = 0.4
TURNED_MIN_YAW = 1.0
MIN_EAR_DIST = 0.01     # ears closer than this (fraction of frame width): yaw is not measurable, use the shoulder fallback
# Shoulder fallback (ears not usable): |nose offset from the shoulder midpoint| / half shoulder width.
MIN_SHOULDER_W = 0.06   # shoulders narrower than this (fraction of frame width) -> too far / too small to judge
FACING_MAX_OFF = 0.35
TURNED_MIN_OFF = 0.85
WINDOW_N = 4            # samples considered for stability
STABLE_N = 3            # samples (of WINDOW_N) that must agree before a label becomes a note
CHANGE_DIFF = 2.0       # mean abs grey difference (0..255) above which two samples count as visibly different
NO_VIDEO_S = 10.0       # caller bound but no frame this long -> visual evaluation unavailable
STALE_S = 3.0           # the newest frame is older than this -> the stream stalled; nothing is classified

DESCRIPTIONS = {
    'facing_camera': 'facing the camera',
    'turned_away': 'turned away from the camera',
    'out_of_frame': 'not visible in the frame',
}
UNAVAILABLE = 'Visual evaluation unavailable: no caller video was received (camera off, denied, or an audio-only call).'


@dataclasses.dataclass
class VisionNote:
    observed_at: float
    source_verified: bool
    observable_description: str
    certainty: str                              # 'clear' | 'uncertain'
    optional_nearby_utterance: str | None = None
    signal: str = ''
    frame_seq: int | None = None
    samples: int = 0

    def as_dict(self):
        return dataclasses.asdict(self)


def classify(lm):
    """(33,5) image landmarks [x, y, z, visibility, presence] or None -> (label, margin). margin in 0..1: how far inside its
    band the measurement sits (used for certainty). 'unknown' means abstain."""
    if lm is None: return 'out_of_frame', 1.0
    vis = lm[:, 3]
    sh_ok = vis[L_SH] >= VIS_MIN and vis[R_SH] >= VIS_MIN
    nose_ok = vis[NOSE] >= VIS_MIN
    if not sh_ok and not nose_ok: return 'out_of_frame', 0.5
    if not nose_ok:                                           # shoulders but no face: back or side to the camera
        sw = abs(lm[L_SH, 0] - lm[R_SH, 0])
        return ('turned_away', 0.5) if sw >= MIN_SHOULDER_W * 0.5 else ('unknown', 0.0)
    ed = abs(lm[L_EAR, 0] - lm[R_EAR, 0])
    if vis[L_EAR] >= VIS_MIN and vis[R_EAR] >= VIS_MIN and ed >= MIN_EAR_DIST:
        yaw = abs(lm[NOSE, 0] - (lm[L_EAR, 0] + lm[R_EAR, 0]) / 2) / (ed / 2)
        if yaw <= FACING_MAX_YAW: return 'facing_camera', float(min(1.0, (FACING_MAX_YAW - yaw) / FACING_MAX_YAW + 0.2))
        if yaw >= TURNED_MIN_YAW: return 'turned_away', float(min(1.0, (yaw - FACING_MAX_YAW) / TURNED_MIN_YAW))
        return 'unknown', 0.0
    if not sh_ok: return 'unknown', 0.0                      # a face, no usable ears and no shoulders: not judged
    sw = abs(lm[L_SH, 0] - lm[R_SH, 0])
    if sw < MIN_SHOULDER_W: return 'unknown', 0.0
    off = abs(lm[NOSE, 0] - (lm[L_SH, 0] + lm[R_SH, 0]) / 2) / (sw / 2)
    if off <= FACING_MAX_OFF: return 'facing_camera', float(min(1.0, (FACING_MAX_OFF - off) / FACING_MAX_OFF + 0.2))
    if off >= TURNED_MIN_OFF: return 'turned_away', float(min(1.0, (off - FACING_MAX_OFF) / TURNED_MIN_OFF))
    return 'unknown', 0.0


def thumb(rgb):
    """32x18 grey thumbnail (float32) for the frame-change check; block means, no OpenCV needed."""
    g = rgb.astype(np.float32).mean(axis=2)
    h, w = g.shape
    ys = np.linspace(0, h, 19).astype(int); xs = np.linspace(0, w, 33).astype(int)
    return np.array([[g[ys[i]:ys[i + 1], xs[j]:xs[j + 1]].mean() for j in range(32)] for i in range(18)], np.float32)


class Observer:
    """Feed it RGB frames (observe) at about 1 fps; it returns a VisionNote when a stable state change happens.
    Pure logic plus an injectable pose callable, so it runs the same live, offline and in tests."""
    def __init__(self, pose=None):
        self.pose = pose                                      # callable(rgb, t_ms) -> (landmarks|None, world) like rtcoach.pose.Pose
        self.window = collections.deque(maxlen=WINDOW_N)
        self.state = None; self.notes = []
        self.n_samples = 0; self.n_new = 0; self.n_changed = 0; self.last_seq = None; self.last_thumb = None
        self.counts = collections.Counter(); self.unavailable = False

    def observe(self, rgb, t, seq=None, lm=None):
        """One sample at job-clock time t. lm: precomputed landmarks (tests); else self.pose runs. Returns a new note or None."""
        self.n_samples += 1
        if seq is None or seq != self.last_seq:
            self.n_new += 1; self.last_seq = seq
        if rgb is not None:
            th = thumb(rgb)
            if self.last_thumb is not None and float(np.abs(th - self.last_thumb).mean()) > CHANGE_DIFF: self.n_changed += 1
            self.last_thumb = th
            if lm is None and self.pose is not None: lm, _ = self.pose(rgb, int(t * 1000))
        label, margin = classify(lm)
        self.counts[label] += 1
        self.window.append((label, margin, t, seq))
        labels = [w[0] for w in self.window]
        top, n = collections.Counter(labels).most_common(1)[0]
        if top == 'unknown' or n < STABLE_N or top == self.state: return None
        agreeing = [w for w in self.window if w[0] == top]
        clear = 'unknown' not in labels and min(w[1] for w in agreeing) >= 0.3   # no unclear sample in the window, none marginal
        self.state = top
        note = VisionNote(observed_at=round(agreeing[0][2], 1), source_verified=True, observable_description=DESCRIPTIONS[top],
                          certainty='clear' if clear else 'uncertain', signal=top, frame_seq=agreeing[0][3], samples=n)
        self.notes.append(note)
        return note

    def mark_unavailable(self, t):
        if self.unavailable: return None
        self.unavailable = True
        note = VisionNote(observed_at=round(t, 1), source_verified=False, observable_description='no caller video received',
                          certainty='clear', signal='no_video')
        self.notes.append(note); return note

    def frame_stats(self):
        return dict(samples=self.n_samples, new_frames=self.n_new, changed=self.n_changed)

    def summary(self):
        """For the end-of-round coach (James P10): plain text built only from what was observed, or the unavailable line."""
        verified = [n for n in self.notes if n.source_verified]
        if not verified:
            if self.n_samples: return (f'Caller video was received ({self.n_samples} samples) but the caller\'s orientation was never clear '
                                       f'enough to judge: no visual feedback.')
            return UNAVAILABLE
        judged = sum(self.counts[k] for k in DESCRIPTIONS)
        parts = [f'{mmss(n.observed_at)} {n.observable_description}' + (' (uncertain)' if n.certainty != 'clear' else '') for n in verified]
        line = 'Camera observations (sampled video frames, body/face orientation only): ' + '; '.join(parts) + '.'
        if judged:
            line += f' Of {judged} samples where the caller could be judged, {self.counts["facing_camera"]} showed them facing the camera.'
        if self.counts['unknown']: line += f' {self.counts["unknown"]} samples were unclear and not judged.'
        return line


def mmss(t):
    return f'{int(t // 60)}:{int(t % 60):02d}'


def attach_utterances(notes, transcript, window_s=5.0):
    """notes: VisionNote list; transcript: iterable of (t, text) caller lines on the same job clock. Sets
    optional_nearby_utterance to the closest caller line within window_s of each verified note. Returns notes."""
    lines = list(transcript)
    for n in notes:
        if not n.source_verified or not lines: continue
        t, text = min(lines, key=lambda x: abs(x[0] - n.observed_at))
        if abs(t - n.observed_at) <= window_s: n.optional_nearby_utterance = text
    return notes


def frame_to_rgb(frame):
    """rtc.VideoFrame -> (h, w, 3) uint8, as facetime/coach_agent.frame_to_rgb (copied: that module imports torch)."""
    from livekit import rtc
    if frame.type != rtc.VideoBufferType.RGB24: frame = frame.convert(rtc.VideoBufferType.RGB24)
    buf = np.frombuffer(frame.data, np.uint8); h, w = frame.height, frame.width
    if len(buf) == h * w * 3: return buf.reshape(h, w, 3)
    return buf.reshape(h, len(buf) // h)[:, :w * 3].reshape(h, w, 3)          # padded rows


def load_pose(variant='lite'):
    from rtcoach.pose import Pose
    return Pose(variant=variant, video=True)


# ---- the worker side: one task per job (facetime/worker.py starts it with --vision-notes) ----
async def run_for_job(job, fps=1.0, variant='lite'):
    """Samples job.latest (frame, ts_us, t_mono, t_wall, seq) at fps once a caller is bound; emits vision_note events.
    Never raises into the job: a failure is logged once and the observer stops (feedback then says video is unavailable)."""
    try:
        pose = await asyncio.to_thread(load_pose, variant)
    except Exception as e:
        print(f'[vision-notes] pose model unavailable ({type(e).__name__}: {e}): no visual notes', flush=True); return
    obs = job.vision_observer = Observer(pose)
    t0 = job.per.t0 if getattr(job, 'per', None) is not None else job.t0
    period = 1.0 / max(0.2, min(fps, 2.0)); bound_t = None
    print(f'[vision-notes] on: {1 / period:g} fps, pose {variant}; signal: facing camera / turned away / out of frame', flush=True)
    try:
        while not job.closed:
            await asyncio.sleep(period)
            now = time.monotonic(); t = now - t0
            if job.bound is None: continue
            if bound_t is None: bound_t = now
            slot = job.latest
            if slot is None:
                if now - bound_t >= NO_VIDEO_S and (note := obs.mark_unavailable(t)) is not None:
                    print(f'[vision-notes] no caller video {NO_VIDEO_S:g} s after the bind: visual evaluation unavailable', flush=True)
                    job.emit('vision_note', **note.as_dict())
                continue
            frame, _ts, t_mono, _wall, seq = slot
            if now - t_mono > STALE_S: continue
            rgb = frame_to_rgb(frame)
            note = await asyncio.to_thread(obs.observe, rgb, t, seq)
            if obs.n_samples % 10 == 0:
                s = obs.frame_stats()
                print(f'[vision-notes] {s["samples"]} samples: {s["new_frames"]} new frames, {s["changed"]} visibly changed; labels {dict(obs.counts)}', flush=True)
            if note is not None:
                print(f'[vision-notes] t={note.observed_at:.1f} {note.observable_description} ({note.certainty}, frame {note.frame_seq})', flush=True)
                job.emit('vision_note', **note.as_dict())
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f'[vision-notes] stopped on an error ({type(e).__name__}: {e}); notes so far are kept', flush=True)
    finally:
        try: pose.close()
        except Exception: pass
        print(f'[vision-notes] end: {obs.frame_stats()}; summary: {obs.summary()}', flush=True)


# ---- offline check ----
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--camera', type=int, help='local webcam index')
    src.add_argument('--video', help='a video file')
    ap.add_argument('--fps', type=float, default=1.0)
    ap.add_argument('--seconds', type=float, default=30.0, help='stop after this long (camera) / this much video')
    ap.add_argument('--pose', default='lite', choices=['lite', 'full', 'heavy'])
    a = ap.parse_args(argv)
    import cv2
    cap = cv2.VideoCapture(a.camera if a.camera is not None else a.video)
    if not cap.isOpened(): print('cannot open the source', file=sys.stderr); return 1
    obs = Observer(load_pose(a.pose))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0; live = a.camera is not None
    t_start = time.monotonic(); n = 0; next_t = 0.0
    while True:
        ok, bgr = cap.read()
        if not ok: break
        t = (time.monotonic() - t_start) if live else n / src_fps; n += 1
        if t > a.seconds: break
        if t < next_t: continue
        next_t = t + 1.0 / a.fps
        note = obs.observe(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), t, seq=n)
        if note is not None: print(f't={note.observed_at:5.1f}  {note.observable_description}  ({note.certainty})', flush=True)
    cap.release()
    print('frames:', obs.frame_stats()); print('labels:', dict(obs.counts)); print(obs.summary())
    return 0


if __name__ == '__main__':
    sys.exit(main())
