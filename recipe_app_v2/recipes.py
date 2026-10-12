"""Read-only recipe detail queries and display values."""
from urllib.parse import urlsplit

from sqlalchemy import func, select

from .config import ROOT
from .uploads import upload_root
from .image_aliases import image_url
from .models import (Collection, Cuisine, Recipe, Recipe_Ingredient,
                     Recipe_Instruction, Recipe_Plan_Date, recipe_collection,
                     recipe_cooked_date, recipe_view_date)


def web_link(value):
    try:
        url = urlsplit(value or "")
        return value if url.scheme.lower() in {"http", "https"} and url.netloc else None
    except ValueError:
        return None


def detail_context(session, recipe_id):
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        return None
    ingredients = session.scalars(select(Recipe_Ingredient).where(
        Recipe_Ingredient.recipe_id == recipe_id).order_by(
        Recipe_Ingredient.sequence, Recipe_Ingredient.recipe_ingredient_id)).all()
    instructions = session.scalars(select(Recipe_Instruction).where(
        Recipe_Instruction.recipe_id == recipe_id, Recipe_Instruction.type == 1).order_by(
        Recipe_Instruction.sequence, Recipe_Instruction.recipe_instruction_id)).all()
    source_notes = session.scalars(select(Recipe_Instruction).where(
        Recipe_Instruction.recipe_id == recipe_id, Recipe_Instruction.type == 2).order_by(
        Recipe_Instruction.sequence, Recipe_Instruction.recipe_instruction_id)).all()
    collections = session.scalars(select(Collection).join(recipe_collection).where(
        recipe_collection.c.recipe_id == recipe_id).order_by(
        Collection.collection_name, Collection.collection_id).distinct()).all()
    cuisine = session.get(Cuisine, recipe.cuisine_id) if recipe.cuisine_id is not None else None
    # Preserve Flask numbering without modifying mapped instruction objects.
    step_count = sum(step.is_group_header == False for step in instructions)
    number = 0
    steps = []
    for step in instructions:
        if step.is_group_header:
            number = 0
            display = step.text_contents
        else:
            number += 1
            display = f"{number}. {step.text_contents}" if step_count > 1 else step.text_contents
        steps.append({"id": step.recipe_instruction_id, "text": display,
                      "is_group_header": bool(step.is_group_header)})
    items = []
    for ingredient in ingredients:
        items.append({"id": ingredient.recipe_ingredient_id, "name": ingredient.name_written,
                      "note": ingredient.note, "is_group_header": bool(ingredient.is_group_header),
                      "image_url": image_url(ingredient.name_official)})
    history = session.execute(select(
        select(func.count()).select_from(recipe_view_date).where(
            recipe_view_date.recipe_id == recipe_id).scalar_subquery(),
        select(func.count()).select_from(recipe_cooked_date).where(
            recipe_cooked_date.recipe_id == recipe_id).scalar_subquery(),
        select(Recipe_Plan_Date.recipe_plan_date_id).where(
            Recipe_Plan_Date.recipe_id == recipe_id, Recipe_Plan_Date.removed_dt.is_(None)).exists(),
    )).one()
    pdf = ROOT / "myrecipes/static/custom_prints" / f"{recipe_id}.pdf"
    return {"recipe": recipe, "ingredients": items, "steps": steps,
            "source_notes": source_notes, "collections": collections, "cuisine": cuisine,
            "ingredient_count": sum(not item["is_group_header"] for item in items),
            "view_count": history[0], "cook_count": history[1], "planned": history[2],
            "source_link": web_link(recipe.source_url), "whisk_link": web_link(recipe.whisk_url),
            "pdf_url": f"/source-pdfs/{recipe_id}.pdf" if pdf.is_file() or
                (upload_root() / 'pdfs' / f'{recipe_id}.pdf').is_file() else None}
