"""Literal, read-only search with AND terms, phrases, exclusions and synonyms."""
import re

from sqlalchemy import func, or_, select

from .models import Ingredient_Synonym, Recipe, Recipe_Ingredient, Recipe_Instruction


def search_terms(query):
    included, excluded = [], []
    excluding = False
    # Tolerate a closing quote not yet entered during live typing.
    for match in re.finditer(r'"([^"\n]*)(?:"|$)|([^\s"]+)', query):
        quoted, word = match.groups()
        if word == "NOT":
            excluding = True
            continue
        term = (quoted if quoted is not None else word).strip()
        if term:
            target = excluded if excluding else included
            if term not in target:
                target.append(term)
    return included, excluded


def contains(column, term):
    return func.lower(column).contains(term.lower(), autoescape=True)


def search_filters(session, query):
    included, excluded = search_terms(query)
    filters = []
    for term, negative in [(t, False) for t in included] + [(t, True) for t in excluded]:
        synonyms = session.execute(select(Ingredient_Synonym.primary_term, Ingredient_Synonym.secondary_term).where(
            or_(contains(Ingredient_Synonym.primary_term, term),
                contains(Ingredient_Synonym.secondary_term, term)))).all()
        ingredient_terms = {term}
        for primary, secondary in synonyms:
            ingredient_terms.update((primary, secondary))
        ingredient_text = func.coalesce(Recipe_Ingredient.name_written, "") + " " + func.coalesce(Recipe_Ingredient.note, "")
        ingredients = select(Recipe_Ingredient.recipe_ingredient_id).where(
            Recipe_Ingredient.recipe_id == Recipe.recipe_id,
            or_(*(contains(ingredient_text, value) for value in sorted(ingredient_terms)))).exists()
        instructions = select(Recipe_Instruction.recipe_instruction_id).where(
            Recipe_Instruction.recipe_id == Recipe.recipe_id,
            contains(Recipe_Instruction.text_contents, term)).exists()
        match = or_(contains(Recipe.name, term), contains(func.coalesce(Recipe.note_from_user, ""), term), ingredients, instructions)
        filters.append(~match if negative else match)
    return filters
