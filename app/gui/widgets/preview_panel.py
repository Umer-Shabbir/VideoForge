"""
Preview panel: shows image thumbnails, subtitle style preview,
transcript segmentation, and triggers sample renders.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QTextEdit, QSizePolicy, QProgressBar,
    QComboBox, QStackedWidget, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QSize
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QFont

from app.core.project import Project, SubtitleMode
from app.gui.theme import COLORS
from app.gui.widgets.common import SectionHeader, TagLabel

log = logging.getLogger("videoforge.preview")


class ThumbnailWidget(QLabel):
    """A single image thumbnail."""
    clicked = Signal(int)  # index

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.setFixedSize(120, 80)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"border: 2px solid {COLORS['border']}; "
            f"border-radius: 4px; background: {COLORS['bg_tertiary']};"
        )
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)

    def set_selected(self, selected: bool):
        color = COLORS['accent'] if selected else COLORS['border']
        self.setStyleSheet(
            f"border: 2px solid {color}; "
            f"border-radius: 4px; background: {COLORS['bg_tertiary']};"
        )


class ImageStripWidget(QWidget):
    """Horizontal scrollable strip of image thumbnails."""
    image_selected = Signal(int)  # index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumbnails: list[ThumbnailWidget] = []
        self._selected = -1
        self._setup_ui()
        self._load_worker: Optional[QThread] = None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFixedHeight(110)
        scroll.setFrameShape(QFrame.NoFrame)

        self._container = QWidget()
        self._h_layout = QHBoxLayout(self._container)
        self._h_layout.setContentsMargins(4, 4, 4, 4)
        self._h_layout.setSpacing(6)
        self._h_layout.addStretch()

        scroll.setWidget(self._container)
        layout.addWidget(scroll)

        self._info_lbl = QLabel("No project selected")
        self._info_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        layout.addWidget(self._info_lbl)

    def load_project(self, project: Project):
        """Load thumbnails for a project asynchronously."""
        self._clear()
        n = len(project.image_paths)
        if n == 0:
            self._info_lbl.setText("No images")
            return

        self._info_lbl.setText(f"{n} image(s)  •  {project.duration_str} audio")

        for i, img_path in enumerate(project.image_paths):
            thumb = ThumbnailWidget(i)
            thumb.clicked.connect(self._on_thumb_clicked)
            thumb.setText(f"#{i+1}")
            self._thumbnails.append(thumb)
            # Insert before stretch
            self._h_layout.insertWidget(i, thumb)
            # Load image in background
            self._load_thumb_async(thumb, img_path, i)

        if self._thumbnails:
            self._select(0)

    def _load_thumb_async(self, thumb: ThumbnailWidget, path: Path, index: int):
        """Load a thumbnail pixmap without blocking the UI."""
        try:
            from PIL import Image
            import io
            with Image.open(path) as img:
                img.thumbnail((240, 160))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                data = buf.read()
            qimg = QImage.fromData(data)
            pix = QPixmap.fromImage(qimg).scaled(
                120, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            thumb.setPixmap(pix)
        except Exception:
            thumb.setText(f"#{index+1}\n{path.suffix}")

    def _clear(self):
        while self._thumbnails:
            t = self._thumbnails.pop()
            self._h_layout.removeWidget(t)
            t.deleteLater()
        self._selected = -1

    def _on_thumb_clicked(self, index: int):
        self._select(index)
        self.image_selected.emit(index)

    def _select(self, index: int):
        if 0 <= self._selected < len(self._thumbnails):
            self._thumbnails[self._selected].set_selected(False)
        self._selected = index
        if 0 <= index < len(self._thumbnails):
            self._thumbnails[index].set_selected(True)


class SubtitlePreviewWidget(QFrame):
    """Shows what subtitles will look like with current settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(160)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        lbl = SectionHeader("Subtitle Preview")
        self._mode_lbl = TagLabel("phrase", COLORS["accent"])
        header.addWidget(lbl)
        header.addWidget(self._mode_lbl)
        header.addStretch()
        layout.addLayout(header)

        # Preview area - dark video-like background
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumHeight(100)
        self._preview.setStyleSheet(
            f"background: #111118; border-radius: 6px; padding: 12px;"
        )
        self._preview.setWordWrap(True)
        layout.addWidget(self._preview, 1)

    def update_preview(self, project: Project):
        """Render a subtitle style preview for this project."""
        if not project.transcript_text:
            self._preview.setText("No transcript — subtitles disabled")
            self._preview.setStyleSheet(
                f"background: #111118; border-radius: 6px; padding: 12px; "
                f"color: {COLORS['text_muted']};"
            )
            return

        mode = project.profile.subtitle_mode
        self._mode_lbl.setText(mode.value)

        # Get a sample chunk
        from app.subtitles.segmenter import segment_text
        chunks = segment_text(
            project.transcript_text[:200],
            mode,
            project.profile.subtitle_max_chars,
            project.profile.subtitle_max_lines
        )
        sample = chunks[1] if len(chunks) > 1 else (chunks[0] if chunks else "Sample subtitle text")

        # Build CSS-like preview
        font_size = max(14, min(30, project.profile.subtitle_font_size // 3))
        weight    = 700 if project.profile.subtitle_bold else 400
        self._preview.setText(sample)
        self._preview.setStyleSheet(
            f"background: #111118; border-radius: 6px; padding: 16px; "
            f"color: #FFFFFF; font-size: {font_size}px; font-weight: {weight};"
        )


class TranscriptSegmentationWidget(QFrame):
    """Shows how the transcript will be segmented into subtitle chunks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(SectionHeader("Transcript Segmentation"))
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        header.addStretch()
        header.addWidget(self._count_lbl)
        layout.addLayout(header)

        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        self._text_view.setMaximumHeight(140)
        self._text_view.setFont(QFont("Consolas", 10))
        self._text_view.setStyleSheet(
            f"background: {COLORS['bg_primary']}; "
            f"color: {COLORS['text_secondary']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px;"
        )
        layout.addWidget(self._text_view)

    def update_preview(self, project: Project):
        if not project.transcript_text:
            self._text_view.setPlainText("No transcript available")
            self._count_lbl.setText("")
            return

        from app.subtitles.segmenter import segment_text
        mode = project.profile.subtitle_mode
        chunks = segment_text(
            project.transcript_text,
            mode,
            project.profile.subtitle_max_chars,
            project.profile.subtitle_max_lines
        )
        self._count_lbl.setText(f"{len(chunks)} chunks")

        lines = []
        for i, chunk in enumerate(chunks[:20]):
            lines.append(f"[{i+1:2d}] {chunk}")
        if len(chunks) > 20:
            lines.append(f"  ... and {len(chunks)-20} more")
        self._text_view.setPlainText("\n".join(lines))


class PreviewPanel(QWidget):
    """
    Full preview panel showing images, subtitle style, transcript segmentation,
    and render metrics for the selected project.
    """
    sample_render_requested = Signal(str)  # project_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_project: Optional[Project] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Title row
        hdr = QHBoxLayout()
        title = QLabel("Preview")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self._project_name_lbl = QLabel("No project selected")
        self._project_name_lbl.setStyleSheet(f"color: {COLORS['text_muted']};")
        hdr.addWidget(title)
        hdr.addWidget(self._project_name_lbl, 1)
        layout.addLayout(hdr)

        # Empty state
        self._empty = QLabel("Select a project to preview")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 14px; padding: 40px;"
        )

        # Content
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        # Image strip
        content_layout.addWidget(SectionHeader("Images"))
        self._image_strip = ImageStripWidget()
        content_layout.addWidget(self._image_strip)

        # Project info cards
        info_row = QHBoxLayout()
        info_row.setSpacing(10)

        self._dur_card = self._make_info_card("Duration", "—")
        self._img_card = self._make_info_card("Images", "—")
        self._words_card = self._make_info_card("Words", "—")
        self._res_card = self._make_info_card("Resolution", "—")
        self._fps_card = self._make_info_card("FPS", "—")
        self._motion_card = self._make_info_card("Motion", "—")

        for c in [self._dur_card, self._img_card, self._words_card,
                  self._res_card, self._fps_card, self._motion_card]:
            info_row.addWidget(c)
        content_layout.addLayout(info_row)

        # Subtitle preview
        self._sub_preview = SubtitlePreviewWidget()
        content_layout.addWidget(self._sub_preview)

        # Transcript segmentation
        self._seg_preview = TranscriptSegmentationWidget()
        content_layout.addWidget(self._seg_preview)

        # Sample render button
        render_row = QHBoxLayout()
        self._sample_btn = QPushButton("▶  Generate 10s Sample Render")
        self._sample_btn.setObjectName("primary")
        self._sample_btn.setFixedHeight(36)
        self._sample_btn.clicked.connect(self._request_sample_render)
        self._sample_btn.setToolTip(
            "Renders the first 10 seconds of this project for a quick preview"
        )
        render_row.addWidget(self._sample_btn)
        render_row.addStretch()
        content_layout.addLayout(render_row)

        content_layout.addStretch()

        # Stack: show either empty state or content
        self._stack = QStackedWidget()
        self._stack.addWidget(self._empty)
        self._stack.addWidget(self._content)
        layout.addWidget(self._stack, 1)

    def _make_info_card(self, label: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumWidth(80)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(10, 8, 10, 8)
        vl.setSpacing(2)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {COLORS['accent_text']};"
        )
        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
        vl.addWidget(val_lbl)
        vl.addWidget(lbl)
        card._value_lbl = val_lbl
        return card

    def set_project(self, project: Optional[Project]):
        """Show preview for the given project."""
        self._current_project = project
        if project is None:
            self._stack.setCurrentIndex(0)
            return

        self._stack.setCurrentIndex(1)
        self._project_name_lbl.setText(project.name)

        # Info cards
        self._dur_card._value_lbl.setText(project.duration_str)
        self._img_card._value_lbl.setText(str(project.image_count))
        self._words_card._value_lbl.setText(
            f"{project.transcript_word_count:,}" if project.transcript_word_count else "—"
        )
        self._res_card._value_lbl.setText(project.profile.resolution_str())
        self._fps_card._value_lbl.setText(str(project.profile.fps))
        self._motion_card._value_lbl.setText(
            project.profile.motion_type.value.replace("_", " ").title()
        )

        # Load images
        self._image_strip.load_project(project)

        # Subtitle preview
        self._sub_preview.update_preview(project)

        # Segmentation
        self._seg_preview.update_preview(project)

    def _request_sample_render(self):
        if self._current_project:
            self.sample_render_requested.emit(self._current_project.id)
