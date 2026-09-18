"""
Consistent labels for entities that carry an ID.

One format everywhere: the ID first in brackets, then the name — "[11] Säröleden
(seg 1/2)". IDs lead because entity names are neither unique nor free of
parentheses, so a trailing "(11)" is easy to lose. Widgets that render rich text
can bold the ID via rich=True; trees can do the same through RichTextDelegate.
"""

from typing import Optional

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

#: IDs longer than this are elided; project IDs are short numbers, imported
#: ones can be UUIDs.
ID_DISPLAY_LENGTH = 12


def format_id(entity_id: Optional[str]) -> str:
    """Shorten an ID for display, keeping short ones intact."""
    if not entity_id:
        return "?"
    text = str(entity_id)
    if len(text) <= ID_DISPLAY_LENGTH:
        return text
    return text[:ID_DISPLAY_LENGTH] + "…"


def entity_label(
    entity_id: Optional[str],
    name: Optional[str] = None,
    kind: Optional[str] = None,
    rich: bool = False,
) -> str:
    """Label an entity as "[id] name", falling back to its kind when unnamed.

    Args:
        entity_id: The entity's ID.
        name: Its name, if it has a non-empty one.
        kind: What it is ("Road", "Polyline", ...), used when there is no name.
        rich: Wrap the ID in <b> for widgets that render HTML.
    """
    ident = format_id(entity_id)
    if rich:
        ident = f"<b>{ident}</b>"
    label = f"[{ident}]"
    trailing = name or kind
    return f"{label} {trailing}" if trailing else label


class RichTextDelegate(QStyledItemDelegate):
    """Item delegate that paints HTML, so tree rows can bold their ID."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        doc = QTextDocument()
        doc.setHtml(opt.text)
        doc.setDocumentMargin(0)
        opt.text = ""

        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        painter.save()
        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget
        )
        painter.translate(text_rect.topLeft())
        # Centre the single text line vertically within the row.
        painter.translate(0, max(0, (text_rect.height() - doc.size().height()) / 2))
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = QTextDocument()
        doc.setHtml(opt.text)
        doc.setDocumentMargin(0)
        return QSize(int(doc.idealWidth()), int(doc.size().height()))


def apply_rich_text_delegate(view) -> None:
    """Render one tree/list view's items as HTML."""
    view.setItemDelegate(RichTextDelegate(view))


__all__ = [
    "ID_DISPLAY_LENGTH",
    "RichTextDelegate",
    "apply_rich_text_delegate",
    "entity_label",
    "format_id",
]
