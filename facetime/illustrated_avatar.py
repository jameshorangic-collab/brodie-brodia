"""Animate the supplied Brodia PNG with the existing idle and PCM mouth renderer.

Remove baked facial marks once in memory; the original PNG remains unchanged.
"""
import cv2
import numpy as np
from PIL import Image
from facetime.brodia_avatar import CharacterAvatar, BOB_STEPS, _over


class IllustratedAvatar(CharacterAvatar):
    def __init__(self, image_path, scenario='park', receptivity='neutral', size=(960, 540)):
        super().__init__(scenario, receptivity, size)
        source = np.array(Image.open(image_path).convert('RGB'))
        if source.shape[:2] != (1317, 1194):
            raise ValueError('Brodia illustration landmarks require the supplied 1194x1317 PNG')
        mask = np.zeros(source.shape[:2], np.uint8)
        for x0, y0, x1, y1 in ((523, 320, 572, 377), (648, 332, 702, 391),
                                 (522, 287, 580, 312), (653, 299, 710, 325),
                                 (560, 386, 645, 446)):
            cv2.rectangle(mask, (x0, y0), (x1, y1), 255, -1)
        clean = cv2.inpaint(source, mask, 5, cv2.INPAINT_TELEA)
        # Upper-body framing makes the face legible on Chert's 640x360 canvas.
        left, top, right, bottom = 260, 105, 935, 770
        crop = Image.fromarray(clean[top:bottom, left:right]).convert('RGBA')
        W, H = self.size
        self.s = min(W * .96 / crop.width, H * .98 / crop.height)
        self.ox = round((W - crop.width * self.s) / 2)
        self.oy = round((H - crop.height * self.s) / 2)
        self.step = max(1, round(self.s))
        self.figure = np.array(crop.resize((round(crop.width * self.s), round(crop.height * self.s)), Image.Resampling.LANCZOS))
        self.bg = np.full((H, W, 3), (241, 232, 215), np.uint8)
        self.plates = [_over(self.bg.copy(), self.figure, self.ox, self.oy - k * self.step) for k in range(BOB_STEPS)]
        def p(x, y): return self.ox + (x-left)*self.s, self.oy + (y-top)*self.s
        self.feat = dict(eyes=[(*p(548, 351), 18*self.s, 24*self.s), (*p(674, 365), 18*self.s, 24*self.s)],
                         brows=[(*p(551, 299), 43*self.s, 8*self.s), (*p(681, 312), 43*self.s, 8*self.s)],
                         mouth=(*p(603, 401), 63*self.s, 22*self.s))
        self.name = 'brodia'; self.label = 'Brodia'; self.ink = (35, 27, 22)

    def _mouth(self, img, dy, shape):
        super()._mouth(img, dy, shape)
        if shape in ('medium', 'wide'):
            cx, cy, w, h = self.feat['mouth']; cy += dy
            cv2.ellipse(img, (round(cx), round(cy + h*.8)), (max(1, round(w*.23)), max(1, round(h*.23))),
                        0, 0, 180, (244, 174, 173), -1, cv2.LINE_AA)
