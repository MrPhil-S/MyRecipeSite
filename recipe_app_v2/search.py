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


def synonym_groups(session):
    # Read once per request; shared spellings connect pairs into one group.
    # Rebuild after every change, without changing the legacy database schema.
    neighbors = {}
    for primary, secondary in session.execute(select(
            Ingredient_Synonym.primary_term, Ingredient_Synonym.secondary_term)):
        primary, secondary = primary.strip().lower(), secondary.strip().lower()
        if not primary or not secondary:
            continue
        neighbors.setdefault(primary, set()).add(secondary)
        neighbors.setdefault(secondary, set()).add(primary)
    unseen = set(neighbors)
    groups = []
    while unseen:
        pending, members = [min(unseen)], set()
        while pending:
            value = pending.pop()
            if value in members:
                continue
            members.add(value)
            pending.extend(neighbors[value] - members)
        unseen.difference_update(members)
        groups.append(sorted(members))
    return groups


def search_filters(session, query):
    included, excluded = search_terms(query)
    groups = synonym_groups(session) if included or excluded else []
    filters = []
    for term, negative in [(t, False) for t in included] + [(t, True) for t in excluded]:
        ingredient_terms = {term}
        for group in groups:
            if any(term.lower() in name for name in group):
                ingredient_terms.update(group)
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
