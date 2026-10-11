document.addEventListener('alpine:init', () => {
  Alpine.data('imageUpload', () => ({
    dragging: false,
    error: '',
    previewUrl: '',
    clearPreview() {
      if (this.previewUrl) URL.revokeObjectURL(this.previewUrl);
      this.previewUrl = '';
    },
    destroy() {
      this.clearPreview();
    },
    choose(files, dropped = false) {
      const input = this.$refs.image;
      this.error = '';
      this.clearPreview();
      input.setCustomValidity('');
      if (!files.length) return;
      const file = files[0];
      if (files.length !== 1) {
        this.error = 'Choose one image at a time.';
      } else if (!['image/jpeg', 'image/png'].includes(file.type)
                 && !(file.type === '' && /\.(jpe?g|png)$/i.test(file.name))) {
        this.error = 'Choose a JPEG or PNG image.';
      } else if (file.size > 8 * 1024 * 1024) {
        this.error = 'Image must be at most 8 MB.';
      }
      if (this.error) {
        input.value = '';
        input.setCustomValidity(this.error);
        return;
      }
      if (dropped) {
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
      }
      this.previewUrl = URL.createObjectURL(file);
    },
    drop(event) {
      this.dragging = false;
      this.choose(event.dataTransfer.files, true);
    }
  }));
});
