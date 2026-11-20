"""Visual Rendering Engine for English Shadowing Videos.

Renders 1920x1080 frames with:
- Warm orange-yellow gradient background with soft wavy curves
- Left 65% text layout with dynamic word pill highlighting
- Top badge (Listen, Your turn, Dialogue, Section, Question)
- Right side illustration area and bottom-right channel logo
- Animated audio waveform bars along the bottom
- Smooth progress bar during silence/your-turn intervals
- Full-screen centered layout for section title cards
"""

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shadowing_pipeline.core.timeline import TimelineEvent


PACKAGE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_THEME_PATH = PACKAGE_DIR / "config" / "theme.json"


class VisualEngine:
    def __init__(self, theme_config_path: Optional[str] = None):
        cfg_path = Path(theme_config_path) if theme_config_path else DEFAULT_THEME_PATH
        if not cfg_path.exists():
            cfg_path = DEFAULT_THEME_PATH

        with open(cfg_path, "r", encoding="utf-8") as f:
            self.theme = json.load(f)

        self.width = self.theme["canvas"]["width"]
        self.height = self.theme["canvas"]["height"]
        self.fps = self.theme["canvas"]["fps"]

        # Load fonts
        font_bold_path = self._resolve_path(self.theme["typography"]["font_bold"])
        font_xbold_path = self._resolve_path(self.theme["typography"]["font_extrabold"])

        self.font_main = ImageFont.truetype(
            font_bold_path, self.theme["typography"]["font_size_main"]
        )
        self.font_title = ImageFont.truetype(
            font_xbold_path, self.theme["typography"]["font_size_title"]
        )
        self.font_badge = ImageFont.truetype(
            font_bold_path, self.theme["typography"]["font_size_badge"]
        )
        self.font_small = ImageFont.truetype(font_bold_path, 22)

        # Pre-render base background
        self.base_background = self._create_base_background()

        # Load static assets
        self.illustration_img = self._load_image(
            self.theme["layout"]["illustration_path"], max_size=(560, 680)
        )
        self.logo_img = self._load_image(
            self.theme["layout"]["logo_path"], max_size=(260, 100)
        )

        # Cache for word wrap layouts: event_id -> layout dict
        self._layout_cache: Dict[int, Dict[str, Any]] = {}

    def _resolve_path(self, rel_path: str) -> str:
        """Finds file relative to workspace root or file itself."""
        p = Path(rel_path)
        if p.exists():
            return str(p.resolve())
        # Try relative to PACKAGE_DIR
        sub = rel_path.replace("backend/", "").replace("shadowing_pipeline/", "")
        pkg_p = PACKAGE_DIR / sub
        if pkg_p.exists():
            return str(pkg_p.resolve())
        # Check assets/images or assets/fonts
        for subfolder in ["assets/images", "assets/fonts", "assets"]:
            cand = PACKAGE_DIR / subfolder / p.name
            if cand.exists():
                return str(cand.resolve())
        root_p = PACKAGE_DIR.parent.parent / rel_path
        if root_p.exists():
            return str(root_p.resolve())
        # Try fallback system fonts if not found
        return "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

    def _load_image(self, rel_path: Optional[str], max_size: Tuple[int, int]) -> Optional[Image.Image]:
        if not rel_path:
            return None
        path = self._resolve_path(rel_path)
        if os.path.exists(path):
            img = Image.open(path).convert("RGBA")
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            return img
        return None

    def _create_base_background(self) -> Image.Image:
        """Loads custom background image (scaled/cropped to 1080p), or falls back to synthetic gradient."""
        bg_path_cfg = self.theme.get("background", {}).get("image_path")
        if bg_path_cfg:
            resolved_bg = self._resolve_path(bg_path_cfg)
            if os.path.exists(resolved_bg):
                im = Image.open(resolved_bg).convert("RGB")
                scale = max(self.width / im.width, self.height / im.height)
                new_w = int(round(im.width * scale))
                new_h = int(round(im.height * scale))
                im_resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
                left = (new_w - self.width) // 2
                top = (new_h - self.height) // 2
                return im_resized.crop((left, top, left + self.width, top + self.height))

        return self._create_wavy_gradient_background()

    def _create_wavy_gradient_background(self) -> Image.Image:
        """Pre-renders 1920x1080 gradient with decorative wavy lines."""
        bg = Image.new("RGB", (self.width, self.height))

        top_col = np.array(self.theme["background"]["gradient_top"], dtype=np.float32)
        bot_col = np.array(self.theme["background"]["gradient_bottom"], dtype=np.float32)

        # Vertical linear gradient
        y_factors = np.linspace(0.0, 1.0, self.height)[:, None, None]
        gradient = top_col + (bot_col - top_col) * y_factors
        grad_img = Image.fromarray(
            np.tile(gradient, (1, self.width, 1)).astype(np.uint8), mode="RGB"
        )
        bg.paste(grad_img, (0, 0))

        # Soft wavy line pattern overlay
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        wave_rgba = tuple(self.theme["background"]["wave_color"])

        for offset in range(-250, self.height + 350, 150):
            points = []
            for x in range(0, self.width + 40, 30):
                y = offset + int(
                    45 * math.sin(x * 0.0032 + offset * 0.008)
                    + 22 * math.cos(x * 0.0065)
                )
                points.append((x, y))
            draw.line(points, fill=wave_rgba, width=self.theme["background"]["wave_thickness"])

        bg.paste(overlay, (0, 0), overlay)
        return bg

    def _get_or_compute_text_layout(self, event: TimelineEvent) -> Dict[str, Any]:
        """Computes and caches word positions and bounding boxes for the 65% left frame."""
        if event.event_id in self._layout_cache:
            return self._layout_cache[event.event_id]

        max_width = int(self.width * self.theme["layout"]["text_area_width_ratio"]) - 60
        start_x = self.theme["layout"]["margin_left"]
        start_y = self.theme["layout"]["margin_top"]
        line_spacing = self.theme["typography"]["line_spacing"]

        font = self.font_main
        # Space width
        space_bbox = font.getbbox(" ")
        space_w = space_bbox[2] - space_bbox[0]

        lines: List[List[Dict[str, Any]]] = [[]]
        curr_x = start_x
        curr_y = start_y

        word_timings = event.word_timings or []
        for w_info in word_timings:
            word = w_info["word"]
            bbox = font.getbbox(word)
            w_width = bbox[2] - bbox[0]
            w_height = bbox[3] - bbox[1]

            if curr_x + w_width > max_width and lines[-1]:
                # Wrap to next line
                curr_y += w_height + line_spacing
                curr_x = start_x
                lines.append([])

            word_entry = {
                "word": word,
                "start": w_info["start"],
                "end": w_info["end"],
                "x": curr_x,
                "y": curr_y,
                "w": w_width,
                "h": w_height,
            }
            lines[-1].append(word_entry)
            curr_x += w_width + space_w

        layout_data = {
            "lines": lines,
            "total_height": (curr_y - start_y) + 70,
        }
        self._layout_cache[event.event_id] = layout_data
        return layout_data

    def render_frame(
        self,
        event: TimelineEvent,
        local_time: float,
        waveform_heights: np.ndarray,
        is_speech: bool,
    ) -> Image.Image:
        """Renders a single frame at the given local event timestamp."""
        # 1. Base background
        frame = self.base_background.copy()
        draw = ImageDraw.Draw(frame, "RGBA")

        # 2. Right-side illustration & Bottom-Right logo
        if self.illustration_img:
            pos = tuple(self.theme["layout"]["illustration_pos"])
            frame.paste(self.illustration_img, pos, self.illustration_img)

        if self.logo_img:
            pos = tuple(self.theme["layout"]["logo_pos"])
            frame.paste(self.logo_img, pos, self.logo_img)

        # 3. Render Content by Subtype
        if event.sub_type == "section_title":
            self._render_section_title(draw, event, local_time)
        else:
            self._render_sentence_view(draw, event, local_time, is_speech)

        # 4. Animated Waveform Bars
        self._render_waveform(draw, waveform_heights, is_speech)

        return frame

    def _render_section_title(
        self, draw: ImageDraw.ImageDraw, event: TimelineEvent, local_time: float
    ):
        """Renders an impactful centered section title card with automatic fitting."""
        cx = int(self.width * 0.50)
        cy = int(self.height * 0.48)

        text = event.text.strip()
        font_path = self._resolve_path(self.theme["typography"]["font_extrabold"])

        chosen_font = self.font_title
        chosen_lines = [text]
        max_card_text_w = 1400

        for f_size in [64, 56, 48, 42, 36]:
            test_font = ImageFont.truetype(font_path, f_size)
            bbox = test_font.getbbox(text)
            text_w = bbox[2] - bbox[0]
            if text_w <= max_card_text_w:
                chosen_font = test_font
                chosen_lines = [text]
                break
            else:
                words = text.split()
                if len(words) > 1:
                    mid = len(words) // 2
                    line1 = " ".join(words[:mid])
                    line2 = " ".join(words[mid:])
                    bb1 = test_font.getbbox(line1)
                    bb2 = test_font.getbbox(line2)
                    w1 = bb1[2] - bb1[0]
                    w2 = bb2[2] - bb2[0]
                    if max(w1, w2) <= max_card_text_w:
                        chosen_font = test_font
                        chosen_lines = [line1, line2]
                        break
        else:
            chosen_font = ImageFont.truetype(font_path, 36)
            chosen_lines = [text]

        line_heights = []
        line_widths = []
        for l in chosen_lines:
            bb = chosen_font.getbbox(l)
            line_widths.append(bb[2] - bb[0])
            line_heights.append(bb[3] - bb[1])

        max_text_w = max(line_widths) if line_widths else 300
        line_spacing = 16
        total_text_h = sum(line_heights) + (len(chosen_lines) - 1) * line_spacing

        badge_text = "SECTION BREAK"
        b_box = self.font_badge.getbbox(badge_text)
        bw = b_box[2] - b_box[0] + 40
        bh = b_box[3] - b_box[1] + 20

        card_w = max(700, min(max_text_w + 140, 1600))
        card_h = bh + total_text_h + 120
        x0 = cx - card_w // 2
        y0 = cy - card_h // 2
        x1 = x0 + card_w
        y1 = y0 + card_h

        draw.rounded_rectangle(
            [x0, y0, x1, y1],
            radius=28,
            fill=tuple(self.theme["colors"]["card_bg"]),
            outline=tuple(self.theme["colors"]["card_outline"]),
            width=3,
        )

        bx = cx - bw // 2
        by = y0 + 32
        draw.rounded_rectangle(
            [bx, by, bx + bw, by + bh],
            radius=16,
            fill=(235, 95, 30, 240),
        )
        draw.text(
            (cx, by + bh // 2 - 2),
            badge_text,
            font=self.font_badge,
            fill=(255, 255, 255),
            anchor="mm",
        )

        curr_text_y = by + bh + 30
        for i, l in enumerate(chosen_lines):
            lh = line_heights[i]
            draw.text(
                (cx, curr_text_y + lh // 2),
                l,
                font=chosen_font,
                fill=tuple(self.theme["colors"]["text_normal"]),
                anchor="mm",
            )
            curr_text_y += lh + line_spacing

    def _render_sentence_view(
        self,
        draw: ImageDraw.ImageDraw,
        event: TimelineEvent,
        local_time: float,
        is_speech: bool,
    ):
        """Renders speech/shadow sentence with badge, text card, and word pill highlighting."""
        # 1. Top Status Badge
        badge_text = event.badge_text
        badge_bg = (
            tuple(self.theme["badges"]["listen"]["bg_color"])
            if is_speech
            else tuple(self.theme["badges"]["your_turn"]["bg_color"])
        )
        if "QUESTION" in badge_text or "ANSWER" in badge_text:
            badge_bg = tuple(self.theme["badges"]["free_answer"]["bg_color"])
        elif event.sub_type == "dialogue":
            badge_bg = tuple(self.theme["badges"]["dialogue"]["bg_color"])

        bx = self.theme["layout"]["margin_left"]
        by = 130
        bbox = self.font_badge.getbbox(badge_text)
        bw = bbox[2] - bbox[0] + 36
        bh = bbox[3] - bbox[1] + 18

        draw.rounded_rectangle(
            [bx, by, bx + bw, by + bh],
            radius=14,
            fill=badge_bg + (240,),
        )
        draw.text(
            (bx + 18, by + 9),
            badge_text,
            font=self.font_badge,
            fill=(255, 255, 255),
        )

        # 2. Text Container Card
        layout = self._get_or_compute_text_layout(event)
        card_x0 = bx - 25
        card_y0 = self.theme["layout"]["margin_top"] - 30
        card_x1 = int(self.width * self.theme["layout"]["text_area_width_ratio"]) + 25
        card_y1 = card_y0 + layout["total_height"] + 50

        draw.rounded_rectangle(
            [card_x0, card_y0, card_x1, card_y1],
            radius=24,
            fill=tuple(self.theme["colors"]["card_bg"]),
            outline=tuple(self.theme["colors"]["card_outline"]),
            width=2,
        )

        # 3. Words and Pill Highlighting
        normal_col = tuple(self.theme["colors"]["text_normal"])
        dimmed_col = tuple(self.theme["colors"]["text_dimmed"])
        pill_bg_col = tuple(self.theme["colors"]["pill_bg"])
        pill_txt_col = tuple(self.theme["colors"]["pill_text"])

        # Determine currently spoken word during speech
        active_word_idx = -1
        if is_speech and event.word_timings:
            for idx, w_info in enumerate(event.word_timings):
                if w_info["start"] <= local_time < w_info["end"]:
                    active_word_idx = idx
                    break
            # If past the last word but still in clip, keep last word active
            if active_word_idx == -1 and local_time >= event.word_timings[-1]["start"]:
                active_word_idx = len(event.word_timings) - 1

        global_w_idx = 0
        for line in layout["lines"]:
            for item in line:
                wx = item["x"]
                wy = item["y"]
                w_str = item["word"]
                ww = item["w"]
                wh = item["h"]

                if not is_speech:
                    # In "Your Turn" pause: all words are clear and readable
                    draw.text((wx, wy), w_str, font=self.font_main, fill=normal_col)
                else:
                    if global_w_idx == active_word_idx:
                        # ACTIVE CURRENT WORD: White rounded pill background + dark text
                        pad_x = 14
                        pad_y = 6
                        pill_rect = [
                            wx - pad_x,
                            wy - pad_y,
                            wx + ww + pad_x,
                            wy + wh + pad_y + 4,
                        ]
                        # Pill with subtle drop shadow
                        draw.rounded_rectangle(
                            [
                                pill_rect[0] + 1,
                                pill_rect[1] + 2,
                                pill_rect[2] + 1,
                                pill_rect[3] + 2,
                            ],
                            radius=12,
                            fill=(0, 0, 0, 25),
                        )
                        draw.rounded_rectangle(
                            pill_rect,
                            radius=12,
                            fill=pill_bg_col + (255,),
                            outline=(255, 235, 180, 255),
                            width=2,
                        )
                        draw.text((wx, wy), w_str, font=self.font_main, fill=pill_txt_col)
                    elif global_w_idx < active_word_idx or active_word_idx == -1:
                        if active_word_idx == -1 and local_time < (event.word_timings[0]["start"] if event.word_timings else 0):
                            # Not yet started
                            draw.text((wx, wy), w_str, font=self.font_main, fill=dimmed_col)
                        else:
                            # Already spoken
                            draw.text((wx, wy), w_str, font=self.font_main, fill=normal_col)
                    else:
                        # Future word: Dimmed
                        draw.text((wx, wy), w_str, font=self.font_main, fill=dimmed_col)

                global_w_idx += 1

    def _render_waveform(
        self, draw: ImageDraw.ImageDraw, bar_heights: np.ndarray, is_speech: bool
    ):
        """Draws animated waveform frequency bars along bottom center."""
        cfg = self.theme["waveform"]
        num_bars = cfg["num_bars"]
        bar_w = cfg["bar_width"]
        gap = cfg["bar_gap"]
        max_h = cfg["max_height"]
        min_h = cfg["min_height"]
        cx = cfg["center_x"]
        by = cfg["bottom_y"]

        total_width = num_bars * bar_w + (num_bars - 1) * gap
        start_x = cx - total_width // 2

        color = (
            tuple(cfg["active_color"]) if is_speech else tuple(cfg["dim_color"])
        )

        for i in range(num_bars):
            val = float(bar_heights[i]) if i < len(bar_heights) else 0.0
            h = min_h + val * (max_h - min_h)
            bx0 = start_x + i * (bar_w + gap)
            by0 = by - h
            bx1 = bx0 + bar_w
            by1 = by

            draw.rounded_rectangle([bx0, by0, bx1, by1], radius=3, fill=color)

