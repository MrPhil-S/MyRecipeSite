FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY recipe_app_v2/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY recipe_app_v2 /app/recipe_app_v2
COPY myrecipes/static/recipe_images /app/myrecipes/static/recipe_images
COPY myrecipes/static/ingredient_images /app/myrecipes/static/ingredient_images
COPY myrecipes/static/custom_prints /app/myrecipes/static/custom_prints
RUN useradd --uid 10001 --create-home recipes \
    && mkdir -p /app/recipe_uploads \
    && chown recipes:recipes /app/recipe_uploads
USER recipes
EXPOSE 8001
CMD ["uvicorn", "recipe_app_v2.main:app", "--host", "0.0.0.0", "--port", "8001"]
