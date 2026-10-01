"""Render the illustrative document-workflow GIF used in the README."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "images" / "document-workflow.gif"
WIDTH, HEIGHT = 1440, 900
COLORS = {
    "paper": "#f3f5f2", "ink": "#202b2a", "muted": "#64736e",
    "green": "#173f3b", "green_light": "#dcebe1", "line": "#cbd4cc",
    "coral": "#bf4c32", "gold": "#cb9332", "blue": "#4683a4",
    "white": "#ffffff", "panel": "#e8ede8", "purple": "#805c90",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows_font = Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf")
    candidates = [windows_font, Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                                    if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


FONTS = {size: font(size) for size in (13, 14, 15, 17, 19, 20, 22, 26, 31)}
FONTS.update({f"b{size}": font(size, True) for size in (13, 14, 15, 17, 19, 20, 22, 26, 31)})


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int = 17,
         color: str | None = None, bold: bool = False) -> None:
    draw.text(xy, value, font=FONTS[f"b{size}" if bold else size],
              fill=color or COLORS["ink"])


def box(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], fill: str,
        outline: str | None = None, radius: int = 8, width: int = 1) -> None:
    draw.rounded_rectangle(rect, radius=radius, fill=fill,
                           outline=outline or fill, width=width)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int],
          color: str = "#739087", width: int = 3) -> None:
    draw.line((start, end), fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) > abs(y2 - y1):
        direction = 1 if x2 > x1 else -1
        points = [(x2, y2), (x2 - 10 * direction, y2 - 6), (x2 - 10 * direction, y2 + 6)]
    else:
        direction = 1 if y2 > y1 else -1
        points = [(x2, y2), (x2 - 6, y2 - 10 * direction), (x2 + 6, y2 - 10 * direction)]
    draw.polygon(points, fill=color)


def base_frame(step: int, title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["paper"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 106), fill=COLORS["green"])
    text(draw, (56, 26), "DOCUMENT WORKBENCH", 15, "#c8decf", True)
    text(draw, (56, 52), title, 26, COLORS["white"], True)
    text(draw, (58, 122), subtitle, 15, COLORS["muted"])

    steps = ["Upload", "Accept", "Process", "Evidence", "Search"]
    x0, gap, y = 58, 260, 178
    for index, label in enumerate(steps):
        x = x0 + index * gap
        active = index == step
        complete = index < step
        fill = COLORS["coral"] if active else COLORS["green"] if complete else COLORS["white"]
        outline = fill if active or complete else COLORS["line"]
        box(draw, (x, y, x + 216, y + 48), fill, outline, radius=6, width=2)
        text(draw, (x + 14, y + 14), f"0{index + 1}  {label}", 15,
             COLORS["white"] if active or complete else COLORS["muted"], True)
        if index < len(steps) - 1:
            arrow(draw, (x + 220, y + 24), (x + gap - 10, y + 24),
                  color=COLORS["coral"] if index < step else "#aebbb5", width=2)
    return image, draw


def frame_upload() -> Image.Image:
    image, draw = base_frame(0, "Start with a document the user provides",
                             "PDF, PNG, or JPEG · metadata is optional · original bytes are retained")
    box(draw, (58, 266, 1382, 748), COLORS["white"], COLORS["line"], 12, 2)
    text(draw, (96, 302), "New document", 22, bold=True)
    text(draw, (96, 365), "PDF, PNG, or JPEG", 13, COLORS["muted"])
    box(draw, (96, 391, 750, 461), "#fbfcfa", COLORS["line"], 5)
    text(draw, (118, 413), "Jordan_Sample_Resume.pdf", 17)
    box(draw, (780, 391, 1328, 461), "#fbfcfa", COLORS["line"], 5)
    text(draw, (804, 413), '{"source":"user_upload"}', 15, COLORS["muted"])
    text(draw, (96, 500), "Document API key", 13, COLORS["muted"])
    box(draw, (96, 526, 650, 596), "#fbfcfa", COLORS["line"], 5)
    text(draw, (118, 548), "••••••••••••••••", 17, COLORS["muted"])
    box(draw, (96, 648, 290, 704), COLORS["coral"], COLORS["coral"], 6)
    text(draw, (120, 666), "Upload document", 17, COLORS["white"], True)
    text(draw, (330, 666), "Validated from file contents, not the filename or browser MIME claim", 15, COLORS["muted"])
    return image


def frame_accepted() -> Image.Image:
    image, draw = base_frame(1, "The API accepts work without waiting for OCR",
                             "POST /api/v1/documents · persist the source + create a durable job · return 201")
    box(draw, (58, 266, 690, 714), COLORS["white"], COLORS["line"], 10, 2)
    text(draw, (92, 302), "Immediate response", 22, bold=True)
    box(draw, (92, 360, 654, 426), COLORS["panel"], COLORS["line"], 5)
    text(draw, (116, 381), "201 Created", 19, COLORS["green"], True)
    response_lines = [
        '"document": {',
        '  "id": "doc_…",',
        '  "status": "PROCESSING",',
        '  "media_type": "application/pdf"',
        '},',
        '"job": { "id": "job_…", "status": "QUEUED" }',
    ]
    for index, line in enumerate(response_lines):
        text(draw, (112, 466 + index * 35), line, 15, "#344d46")
    box(draw, (764, 266, 1382, 475), COLORS["green_light"], "#99b9a4", 10, 2)
    text(draw, (806, 302), "Original source", 22, bold=True)
    text(draw, (806, 350), "Atomic file write", 17, COLORS["muted"])
    text(draw, (806, 389), "Immutable upload bytes", 17, COLORS["muted"])
    text(draw, (806, 428), "Generated server-side filename", 17, COLORS["muted"])
    box(draw, (764, 510, 1382, 714), "#fff0ce", "#d8b56b", 10, 2)
    text(draw, (806, 548), "SQLite job record", 22, bold=True)
    text(draw, (806, 600), "QUEUED  →  PROCESSING  →  terminal state", 17, COLORS["muted"])
    text(draw, (806, 650), "Request has already returned", 17, COLORS["coral"], True)
    arrow(draw, (690, 575), (764, 575))
    return image


def frame_processing() -> Image.Image:
    image, draw = base_frame(2, "A background worker runs the pipeline",
                             "Progress reflects persisted work · percentages remain null when not calculable")
    stages = [
        ("VALIDATION", "signature + integrity", True),
        ("PREPROCESSING", "resize · denoise · deskew", True),
        ("OCR", "Tesseract page blocks", True),
        ("ENTITY_EXTRACTION", "evidence-linked entities", False),
        ("INDEXING", "SQLite FTS5", False),
    ]
    y = 276
    for index, (name, detail, done) in enumerate(stages):
        active = index == 2
        fill = COLORS["green_light"] if done else COLORS["white"]
        outline = COLORS["coral"] if active else COLORS["line"]
        box(draw, (118, y, 1020, y + 74), fill, outline, 7, 3 if active else 1)
        box(draw, (144, y + 21, 174, y + 51), COLORS["green"] if done else COLORS["white"],
            COLORS["green"] if done else COLORS["line"], 15, 2)
        text(draw, (202, y + 14), name, 17, COLORS["green"] if done else COLORS["muted"], True)
        text(draw, (545, y + 17), detail, 15, COLORS["muted"])
        if index < len(stages) - 1:
            arrow(draw, (160, y + 75), (160, y + 96), width=2)
        y += 98
    box(draw, (1080, 276, 1382, 665), COLORS["white"], COLORS["line"], 10, 2)
    text(draw, (1110, 310), "Observed state", 19, bold=True)
    text(draw, (1110, 376), "PROCESSING", 17, COLORS["coral"], True)
    text(draw, (1110, 424), "stage", 13, COLORS["muted"])
    text(draw, (1110, 448), "OCR", 22, bold=True)
    text(draw, (1110, 502), "pages", 13, COLORS["muted"])
    text(draw, (1110, 526), "1 / 1", 22, bold=True)
    box(draw, (1110, 585, 1350, 599), COLORS["panel"], COLORS["panel"], 7)
    box(draw, (1110, 585, 1260, 599), COLORS["coral"], COLORS["coral"], 7)
    text(draw, (1110, 621), "Illustrative progress", 13, COLORS["muted"])
    return image


def frame_evidence() -> Image.Image:
    image, draw = base_frame(3, "Every extracted entity carries source evidence",
                             "Select an entity to inspect the OCR text, page, and bounding box")
    box(draw, (58, 266, 796, 746), COLORS["white"], COLORS["line"], 10, 2)
    text(draw, (92, 302), "Page 1 · OCR blocks", 22, bold=True)
    lines = [
        "Jordan Sample",
        "jordan.sample@example.test",
        "Company: Northstar Robotics",
        "Skills: Python, SQL, Docker",
    ]
    for index, value in enumerate(lines):
        top = 367 + index * 70
        box(draw, (96, top, 740, top + 48), "#edf3ef", "#c4d5ca", 4)
        text(draw, (114, top + 13), value, 17)
    box(draw, (842, 266, 1382, 746), COLORS["white"], COLORS["line"], 10, 2)
    text(draw, (878, 302), "Extracted entities", 22, bold=True)
    entities = [("PERSON", "Jordan Sample"), ("EMAIL", "jordan.sample@example.test"),
                ("ORGANIZATION", "Northstar Robotics"), ("SKILL", "Python")]
    for index, (kind, value) in enumerate(entities):
        top = 363 + index * 72
        selected = index == 3
        fill = "#fff0ce" if selected else "#f5f7f4"
        outline = COLORS["gold"] if selected else COLORS["line"]
        box(draw, (878, top, 1348, top + 52), fill, outline, 5, 2 if selected else 1)
        text(draw, (894, top + 5), kind, 13, COLORS["muted"], True)
        text(draw, (894, top + 26), value, 15)
    text(draw, (878, 676), "Evidence → page 1 → OCR block + bbox", 14, COLORS["green"], True)
    return image


def frame_search() -> Image.Image:
    image, draw = base_frame(4, "Search returns matching pages and entities",
                             "GET /api/v1/search?q=Python · cursor pagination · empty results are still 200 OK")
    box(draw, (58, 266, 1382, 390), COLORS["white"], COLORS["line"], 10, 2)
    text(draw, (96, 296), "Search processed documents", 15, COLORS["muted"])
    box(draw, (96, 328, 1100, 372), "#fbfcfa", COLORS["line"], 4)
    text(draw, (114, 340), "Python", 17)
    box(draw, (1128, 328, 1328, 372), COLORS["coral"], COLORS["coral"], 4)
    text(draw, (1184, 340), "Search", 15, COLORS["white"], True)
    box(draw, (58, 424, 1382, 736), COLORS["white"], COLORS["line"], 10, 2)
    text(draw, (96, 458), "1 matching document", 20, bold=True)
    box(draw, (96, 510, 1340, 674), "#edf3ef", "#c4d5ca", 7, 1)
    text(draw, (124, 532), "Jordan_Sample_Resume.pdf", 19, COLORS["green"], True)
    text(draw, (124, 580), "TEXT · page 1", 13, COLORS["muted"], True)
    text(draw, (124, 608), "Skills: Python, SQL, Docker", 17)
    text(draw, (124, 644), "bbox: top-left pixel coordinates · source page retained", 14, COLORS["muted"])
    box(draw, (96, 690, 298, 724), COLORS["green_light"], "#9db9a5", 4)
    text(draw, (112, 699), "COMPLETED", 13, COLORS["green"], True)
    return image


def main() -> None:
    frames = [frame_upload(), frame_accepted(), frame_processing(), frame_evidence(), frame_search()]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=[1800, 1800, 2200, 2200, 2400],
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Rendered {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()