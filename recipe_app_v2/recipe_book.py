"""Generate a printable book from the recipes in the active FastAPI database."""
from datetime import date
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from PIL import Image as PILImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as PDFImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_session
from .models import Recipe, Recipe_Ingredient, Recipe_Instruction
from .uploads import upload_root

router = APIRouter()
PACKAGE = Path(__file__).resolve().parent


def _text(value):
    """Escape recipe text for ReportLab Paragraph markup and normalize fractions."""
    value = str(value or "")
    fractions = {
        "\u00bc": "1/4", "\u00bd": "1/2", "\u00be": "3/4",
        "\u2153": "1/3", "\u2154": "2/3", "\u215b": "1/8",
        "\u215c": "3/8", "\u215d": "5/8", "\u215e": "7/8",
    }
    for source, replacement in fractions.items():
        value = value.replace(source, replacement)
    return escape(value).replace("\n", "<br/>")


def _photo_path(recipe):
    filename = recipe.image_file or ""
    if not filename or Path(filename).name != filename or filename in (".", ".."):
        return None
    candidate = upload_root() / "images" / filename
    if candidate.is_file():
        return candidate
    return None


def _styles():
    styles = getSampleStyleSheet()
    font_path = PACKAGE / "static/fonts/dm-sans.ttf"
    font_name = "Helvetica"
    if font_path.is_file():
        try:
            pdfmetrics.registerFont(TTFont("RecipeBookDMSans", str(font_path)))
            pdfmetrics.registerFontFamily("RecipeBookDMSans", normal="RecipeBookDMSans",
                                          bold="RecipeBookDMSans", italic="RecipeBookDMSans",
                                          boldItalic="RecipeBookDMSans")
            font_name = "RecipeBookDMSans"
        except (OSError, ValueError):
            pass

    ink = colors.HexColor("#22252a")
    accent = colors.HexColor("#8c3544")
    muted = colors.HexColor("#626a75")
    styles.add(ParagraphStyle(name="BookTitle", parent=styles["Title"], fontName=font_name,
                              fontSize=28, leading=34, textColor=ink, alignment=TA_CENTER,
                              spaceAfter=12))
    styles.add(ParagraphStyle(name="BookSubtitle", parent=styles["Normal"], fontName=font_name,
                              fontSize=11, leading=16, textColor=muted, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="RecipeTitle", parent=styles["Heading1"], fontName=font_name,
                              fontSize=24, leading=29, textColor=ink, spaceAfter=6))
    styles.add(ParagraphStyle(name="RecipeMeta", parent=styles["Normal"], fontName=font_name,
                              fontSize=9, leading=13, textColor=muted, spaceAfter=10))
    styles.add(ParagraphStyle(name="RecipeSection", parent=styles["Heading2"], fontName=font_name,
                              fontSize=15, leading=19, textColor=accent, spaceBefore=12,
                              spaceAfter=6, keepWithNext=True))
    styles.add(ParagraphStyle(name="RecipeBody", parent=styles["BodyText"], fontName=font_name,
                              fontSize=9.5, leading=14, textColor=ink, spaceAfter=5))
    styles.add(ParagraphStyle(name="RecipeNote", parent=styles["BodyText"], fontName=font_name,
                              fontSize=8.5, leading=12, textColor=muted, spaceAfter=4))
    return styles, font_name, muted


def _recipe_rows(session):
    recipes = session.scalars(select(Recipe).order_by(func.lower(Recipe.name), Recipe.recipe_id)).all()
    if not recipes:
        return []
    recipe_ids = [recipe.recipe_id for recipe in recipes]
    ingredients = session.scalars(select(Recipe_Ingredient).where(
        Recipe_Ingredient.recipe_id.in_(recipe_ids)).order_by(
        Recipe_Ingredient.recipe_id, Recipe_Ingredient.sequence,
        Recipe_Ingredient.recipe_ingredient_id)).all()
    instructions = session.scalars(select(Recipe_Instruction).where(
        Recipe_Instruction.recipe_id.in_(recipe_ids),
        Recipe_Instruction.type == 1).order_by(
        Recipe_Instruction.recipe_id, Recipe_Instruction.sequence,
        Recipe_Instruction.recipe_instruction_id)).all()
    source_notes = session.scalars(select(Recipe_Instruction).where(
        Recipe_Instruction.recipe_id.in_(recipe_ids),
        Recipe_Instruction.type == 2).order_by(
        Recipe_Instruction.recipe_id, Recipe_Instruction.sequence,
        Recipe_Instruction.recipe_instruction_id)).all()

    ingredients_by_recipe = {}
    instructions_by_recipe = {}
    notes_by_recipe = {}
    for row in ingredients:
        ingredients_by_recipe.setdefault(row.recipe_id, []).append(row)
    for row in instructions:
        instructions_by_recipe.setdefault(row.recipe_id, []).append(row)
    for row in source_notes:
        notes_by_recipe.setdefault(row.recipe_id, []).append(row)
    return [(recipe, ingredients_by_recipe.get(recipe.recipe_id, []),
             instructions_by_recipe.get(recipe.recipe_id, []),
             notes_by_recipe.get(recipe.recipe_id, [])) for recipe in recipes]


def _build_recipe_book(recipes):
    if not recipes:
        return b""
    styles, font_name, muted = _styles()
    stream = BytesIO()
    document = SimpleDocTemplate(
        stream, pagesize=letter, rightMargin=.68 * inch, leftMargin=.68 * inch,
        topMargin=.55 * inch, bottomMargin=.55 * inch,
        title="My Recipes - recipe book", author="My Recipes")
    logo_path = PACKAGE / "static/brand/my-recipes.png"
    story = [Spacer(1, 1.25 * inch)]
    if logo_path.is_file():
        # At 5.8 inches wide, the 2172px source prints at about 375 dpi.
        story.extend([PDFImage(str(logo_path), width=5.8 * inch, height=1.95 * inch,
                               kind="proportional", hAlign="CENTER"), Spacer(1, .25 * inch)])
    else:
        story.append(Paragraph("My Recipes", styles["BookTitle"]))
    story.extend([
        Paragraph(f"Recipe book<br/>{len(recipes)} recipes | generated {date.today():%B %d, %Y}",
                  styles["BookSubtitle"]),
        Spacer(1, .28 * inch),
        Paragraph("A printable collection of recipes from your library.", styles["BookSubtitle"]),
        PageBreak(),
    ])

    for index, (recipe, ingredients, instructions, notes) in enumerate(recipes):
        if index:
            story.append(PageBreak())
        story.append(Paragraph(_text(recipe.name), styles["RecipeTitle"]))
        metadata = [label for label, value in (
            (f"Prep {recipe.prep_time}", recipe.prep_time),
            (f"Cook {recipe.cook_time}", recipe.cook_time),
            (f"Total {recipe.total_time}", recipe.total_time),
            (f"Serves {recipe.servings}", recipe.servings),
        ) if value not in (None, "")]
        story.append(Paragraph(_text("  |  ".join(metadata)), styles["RecipeMeta"]))

        photo = _photo_path(recipe)
        if photo:
            try:
                with PILImage.open(photo) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    image.thumbnail((1500, 1100))
                    image_bytes = BytesIO()
                    image.save(image_bytes, format="JPEG", quality=80, optimize=True)
                image_bytes.seek(0)
                story.extend([PDFImage(image_bytes, width=5.7 * inch, height=2.35 * inch,
                                       kind="proportional", hAlign="LEFT"), Spacer(1, 6)])
            except (OSError, ValueError):
                # One broken/missing photo should not prevent printing the book.
                pass

        story.append(Paragraph("Ingredients", styles["RecipeSection"]))
        for ingredient in ingredients:
            if ingredient.is_group_header:
                line = f"<b>{_text(ingredient.name_written)}</b>"
            else:
                line = f"&#8226; {_text(ingredient.name_written)}"
                if ingredient.note:
                    line += f' <font color="#626a75">({_text(ingredient.note)})</font>'
            story.append(Paragraph(line, styles["RecipeBody"]))

        if instructions:
            story.append(Paragraph("Instructions", styles["RecipeSection"]))
            step_number = 0
            for step in instructions:
                if step.is_group_header:
                    story.append(Paragraph(f"<b>{_text(step.text_contents)}</b>", styles["RecipeBody"]))
                    step_number = 0
                else:
                    step_number += 1
                    line = (f'<font color="#8c3544"><b>{step_number:02d}</b></font>  '
                            f"{_text(step.text_contents)}")
                    story.append(Paragraph(line, styles["RecipeBody"]))

        if notes:
            story.append(Paragraph("Source notes", styles["RecipeSection"]))
            for note in notes:
                story.append(Paragraph(_text(note.text_contents), styles["RecipeNote"]))
        if recipe.note_from_user:
            story.append(Paragraph("Your notes", styles["RecipeSection"]))
            story.append(Paragraph(_text(recipe.note_from_user), styles["RecipeNote"]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(muted)
        canvas.setFont(font_name, 8)
        canvas.drawString(doc.leftMargin, .34 * inch, "My Recipes")
        canvas.drawRightString(letter[0] - doc.rightMargin, .34 * inch, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


@router.get("/recipe-book", response_class=HTMLResponse)
def recipe_book_page(request: Request, session: Session = Depends(get_session)):
    count = session.scalar(select(func.count()).select_from(Recipe)) or 0
    from .main import templates
    return templates.TemplateResponse(request=request, name="recipe_book.html",
                                      context={"recipe_count": count})


@router.get("/recipe-book.pdf")
def recipe_book_pdf(session: Session = Depends(get_session)):
    pdf = _build_recipe_book(_recipe_rows(session))
    if not pdf:
        return Response("There are no recipes to print yet.", status_code=404,
                        media_type="text/plain; charset=utf-8")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="my-recipes-recipe-book.pdf"',
                             "Cache-Control": "no-store"})
