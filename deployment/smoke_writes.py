"""One owned production fixture through HTTP; remove its DB rows and uploads."""

import io
import os
import re
import secrets
import sys

import httpx
from PIL import Image
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from recipe_app_v2.activity import delete_recipe_data, deletion_version
from recipe_app_v2.database import get_write_engine
from recipe_app_v2.models import Recipe
from recipe_app_v2.uploads import upload_root
from recipe_app_v2.verify_editor import FormParser


BASE = "http://192.168.1.13:5000"


def fields(body):
    return dict(FormParser(body).fields)


def image():
    output = io.BytesIO()
    Image.new("RGB", (16, 16), "#8c3544").save(output, format="PNG")
    return output.getvalue()


def pdf():
    output = io.BytesIO()
    document = canvas.Canvas(output)
    document.drawString(40, 740, "My Recipes deployment fixture")
    document.save()
    return output.getvalue()


def expect_redirect(response, prefix):
    assert response.status_code == 303, (response.status_code, response.text[:300])
    assert response.headers["location"].startswith(prefix), response.headers["location"]


def main():
    if sys.argv[1:] != ["--execute"]:
        raise SystemExit("Explicit --execute is required for the production write smoke check.")
    assert os.environ.get("RECIPE_APP_ENV") == "production"
    assert os.environ.get("RECIPE_PROD_WRITES") == "1"
    prefix = "Deployment check " + secrets.token_hex(8)
    recipe_id = None
    image_file = None
    owned = False
    try:
        with httpx.Client(base_url=BASE, timeout=30, follow_redirects=False,
                          headers={"Origin": BASE}) as client:
            health = client.get("/health").json()
            assert health["environment"] == "production"
            assert health["database"] == "MyRecipes" and health["saves_enabled"]

            token = fields(client.get("/recipes/new").text)["csrf_token"]
            data = {
                "csrf_token": token, "version": "", "name": prefix,
                "source_url": "", "whisk_url": "", "prep_time": "5 mins",
                "cook_time": "", "additional_time": "", "servings": "1",
                "cuisine_id": "", "ingredient_mode": "bulk",
                "ingredient_bulk": "1 tsp salt", "instructions": "Stir",
                "source_notes": "", "note_from_user": "Deployment fixture",
            }
            response = client.post("/recipes/new", data=data, files={
                "image": ("fixture.png", image(), "image/png"),
                "pdf": ("fixture.pdf", pdf(), "application/pdf"),
            })
            expect_redirect(response, "/recipes/")
            recipe_id = int(response.headers["location"].rsplit("/", 1)[1])
            print("created_fixture_id=" + str(recipe_id))

            with Session(get_write_engine()) as session:
                recipe = session.get(Recipe, recipe_id)
                assert recipe is not None and recipe.name == prefix
                assert re.fullmatch(r"[0-9a-f]{16}\.jpg", recipe.image_file)
                image_file = recipe.image_file
                owned = True

            assert client.get(f"/recipe-images/{image_file}").status_code == 200
            assert client.get(f"/source-pdfs/{recipe_id}.pdf").status_code == 200

            edit = fields(client.get(f"/recipes/{recipe_id}/edit").text)
            data.update(csrf_token=edit["csrf_token"], version=edit["version"],
                        name=prefix + " edited", note_from_user="Verified edit")
            expect_redirect(client.post(f"/recipes/{recipe_id}/edit", data=data),
                            f"/recipes/{recipe_id}")

            for action in ("plan-add", "cooked", "favorite-add"):
                response = client.post(f"/recipes/{recipe_id}/actions/{action}", data={
                    "csrf_token": edit["csrf_token"],
                    "return_to": f"/recipes/{recipe_id}",
                })
                expect_redirect(response, f"/recipes/{recipe_id}")

            detail = client.get(f"/recipes/{recipe_id}?log_visit=false")
            assert detail.status_code == 200 and "Verified edit" in detail.text
            confirmation = fields(client.get(f"/recipes/{recipe_id}/delete").text)
            expect_redirect(client.post(f"/recipes/{recipe_id}/delete", data={
                "csrf_token": confirmation["csrf_token"],
                "version": confirmation["version"],
                "return_to": confirmation.get("return_to", "/"),
            }), "/")
            assert client.get(f"/recipes/{recipe_id}?log_visit=false").status_code == 404
            print("HTTP_CREATE_EDIT_ACTION_DELETE_OK")
    finally:
        # Recover a fixture even if an HTTP step failed after its creation.
        with Session(get_write_engine()) as session:
            matches = session.scalars(select(Recipe).where(
                Recipe.name.in_((prefix, prefix + " edited")))).all()
            assert len(matches) <= 1, "Fixture ownership is ambiguous; manual review required."
            if matches:
                recipe = matches[0]
                recipe_id = recipe.recipe_id
                owned = True
                if re.fullmatch(r"[0-9a-f]{16}\.jpg", recipe.image_file or ""):
                    image_file = recipe.image_file
                version = deletion_version(session, recipe)
            else:
                version = None
        if version is not None:
            delete_recipe_data(recipe_id, version)
        if owned and recipe_id is not None:
            if image_file:
                (upload_root() / "images" / image_file).unlink(missing_ok=True)
            (upload_root() / "pdfs" / f"{recipe_id}.pdf").unlink(missing_ok=True)
            print("FIXTURE_AND_UPLOADS_CLEANED")


if __name__ == "__main__":
    main()
