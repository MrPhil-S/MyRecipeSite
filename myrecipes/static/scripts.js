document.querySelectorAll(".drop-zone__input").forEach((inputElement) => {
	const dropZoneElement = inputElement.closest(".drop-zone");

	dropZoneElement.addEventListener("click", (e) => {
		inputElement.click();
	});

	inputElement.addEventListener("change", (e) => {
		if (inputElement.files.length) {
			updateThumbnail(dropZoneElement, inputElement.files[0]);
		}
	});

	dropZoneElement.addEventListener("dragover", (e) => {
		e.preventDefault();
		dropZoneElement.classList.add("drop-zone--over");
	});

	["dragleave", "dragend"].forEach((type) => {
		dropZoneElement.addEventListener(type, (e) => {
			dropZoneElement.classList.remove("drop-zone--over");
		});
	});

	dropZoneElement.addEventListener("drop", (e) => {
		e.preventDefault();

		if (e.dataTransfer.files.length) {
			inputElement.files = e.dataTransfer.files;
			updateThumbnail(dropZoneElement, e.dataTransfer.files[0]);
		}

		dropZoneElement.classList.remove("drop-zone--over");
	});
});

/**
 * Updates the thumbnail on a drop zone element.
 *
 * @param {HTMLElement} dropZoneElement
 * @param {File} file
 */
function updateThumbnail(dropZoneElement, file) {
	let thumbnailElement = dropZoneElement.querySelector(".drop-zone__thumb");

	// First time - remove the prompt
	if (dropZoneElement.querySelector(".drop-zone__prompt")) {
		dropZoneElement.querySelector(".drop-zone__prompt").remove();
	}

	// First time - there is no thumbnail element, so lets create it
	if (!thumbnailElement) {
		thumbnailElement = document.createElement("div");
		thumbnailElement.classList.add("drop-zone__thumb");
		dropZoneElement.appendChild(thumbnailElement);
	}

	thumbnailElement.dataset.label = file.name;

	// Show thumbnail for image files
	if (file.type.startsWith("image/")) {
		const reader = new FileReader();

		reader.readAsDataURL(file);
		reader.onload = () => {
			thumbnailElement.style.backgroundImage = `url('${reader.result}')`;
		};
	} else {
		thumbnailElement.style.backgroundImage = null;
	}
}

//Horizontal scrolling for collections on home page
var scrollingWrapper = document.getElementById('scrollingWrapper');
var scrollLeftIcon = document.getElementById('scrollLeftIcon');
var scrollRightIcon = document.getElementById('scrollRightIcon');

	if (scrollingWrapper && scrollLeftIcon && scrollRightIcon) {

	// Add event listener for the left arrow icon
	scrollLeftIcon.addEventListener('click', function() {
		// Scroll the container to the left by a certain amount (adjust as needed)
		scrollingWrapper.scrollLeft -= 300;
	});

	// Add event listener for the right arrow icon
	scrollRightIcon.addEventListener('click', function() {
		// Scroll the container to the right by a certain amount (adjust as needed)
		scrollingWrapper.scrollLeft += 300;
	});
}




//Start add/edit recipe radio buttons toggle
// Get radio buttons and sections
const individualRadio = document.getElementById('individualMethod');
const bulkRadio = document.getElementById('bulkMethod');
const individualSection = document.getElementById('individualIngredients');
const bulkSection = document.getElementById('bulkAdd');

if (individualRadio && individualSection && bulkSection) {

// Function to toggle visibility based on the selected option
	function toggleSections() {
			if (individualRadio.checked) {
					individualSection.style.display = 'block';
					bulkSection.style.display = 'none';
			} else {
					individualSection.style.display = 'none';
					bulkSection.style.display = 'block';
			}
	}

	// Initial state check
		toggleSections();

		// Add event listeners for radio buttons
		individualRadio.addEventListener('change', toggleSections);
		bulkRadio.addEventListener('change', toggleSections);

		//End add/edit recipe radio buttons toggle
}