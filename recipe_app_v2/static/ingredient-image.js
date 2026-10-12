document.addEventListener('alpine:init', () => {
  Alpine.data('ingredientImage', (rowId, selectedName = '', selectedUrl = '') => ({
    proposal: null, selectedName, selectedUrl, error: '', busy: false, generation: 0,
    clear() {
      this.generation++;
      this.proposal = null;
      this.selectedName = '';
      this.error = '';
      this.busy = false;
      this.$refs.imageToken.value = '';
    },
    async preview() {
      this.clear();
      const generation = this.generation;
      const row = this.$refs.imageToken.closest('.ingredient-row');
      const form = row.closest('form');
      this.busy = true;
      try {
        const response = await fetch('/editor/ingredient-image-preview', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            recipe_id: form.querySelector('[name="recipe_id"]').value, row_id: rowId,
            name: row.querySelector('[name="ingredient_name"]').value,
            version: form.querySelector('[name="version"]').value,
            csrf_token: form.querySelector('[name="csrf_token"]').value
          })
        });
        const result = await response.json();
        if (generation !== this.generation) return;
        if (!response.ok) throw new Error(result.detail || 'Unable to preview this image.');
        this.proposal = result;
      } catch (error) {
        if (generation === this.generation) this.error = error.message;
      } finally {
        if (generation === this.generation) this.busy = false;
      }
    },
    accept() {
      if (!this.proposal?.token || !this.proposal.changed) return;
      this.$refs.imageToken.value = this.proposal.token;
      this.selectedName = this.proposal.name;
      this.selectedUrl = this.proposal.image;
      this.proposal = null;
    }
  }));
});
