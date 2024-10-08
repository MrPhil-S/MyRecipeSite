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

//Search Recipes dropdown
$(document).ready(function() {
	// Handle each type-ahead input with its respective dropdown
	$('.typeahead-input').each(function() {
			const inputField = $(this);
			const dropdownMenu = inputField.siblings('.dropdown-menu');
			let currentIndex = -1; // Track the index of the highlighted option
			const form = inputField.closest('form'); // Get the closest form element

			// Show dropdown when input field is focused
			inputField.on('focus', function() {
					dropdownMenu.addClass('show'); // Show dropdown on focus
					currentIndex = -1; // Reset currentIndex when the dropdown is shown
					dropdownMenu.children('.dropdown-item').removeClass('active'); // Remove active class
			});

			// Hide dropdown when input field loses focus
			inputField.on('blur', function() {
					setTimeout(function() {
							dropdownMenu.removeClass('show'); // Hide after a brief delay
					}, 200); // Delay to allow for item click
			});

			// Show/Hide dropdown based on input
			inputField.on('input', function() {
					const inputValue = $(this).val().toLowerCase();
					let hasMatches = false;

					// Show or hide dropdown items based on match
					dropdownMenu.children('.dropdown-item').each(function() {
							const optionText = $(this).text().toLowerCase();
							if (optionText.includes(inputValue)) {
									$(this).show();
									hasMatches = true;
							} else {
									$(this).hide();
							}
					});

					if (hasMatches) {
							dropdownMenu.addClass('show');
					} else {
							dropdownMenu.removeClass('show');
					}

					currentIndex = -1; // Reset index when input changes
					dropdownMenu.children('.dropdown-item').removeClass('active'); // Remove active class
			});

			// Handle key navigation and Escape key
			inputField.on('keydown', function(e) {
					const items = dropdownMenu.children('.dropdown-item:visible'); // Only visible items

					if (e.key === 'ArrowDown') {
							e.preventDefault();
							if (currentIndex < items.length - 1) {
									currentIndex++;
									highlightOption(items, currentIndex);
							}
					} else if (e.key === 'ArrowUp') {
							e.preventDefault();
							if (currentIndex > 0) {
									currentIndex--;
									highlightOption(items, currentIndex);
							}
					} else if (e.key === 'Enter') {
							e.preventDefault();
							if (currentIndex >= 0) {
									const selectedText = items.eq(currentIndex).text(); // Get the highlighted item's text
									inputField.val(selectedText); // Set input field value
									dropdownMenu.removeClass('show'); // Hide dropdown
									currentIndex = -1; // Reset index
							}
							// Submit the form
							form.submit(); // Submit the form when Enter is pressed
					} else if (e.key === 'Escape') {
							e.preventDefault();
							dropdownMenu.removeClass('show'); // Hide dropdown on Escape
					}
			});

			// Handle click on dropdown item to populate input
			dropdownMenu.on('mousedown', '.dropdown-item', function(e) {
					e.preventDefault(); // Prevent losing focus too soon
					const selectedText = $(this).text(); // Get clicked item's text
					inputField.val(selectedText); // Set input field value
					dropdownMenu.removeClass('show'); // Hide dropdown
					form.submit(); // Submit the form when an item is selected
			});

			// Function to highlight the option
			function highlightOption(items, index) {
					items.removeClass('active'); // Remove active class from all
					items.eq(index).addClass('active'); // Add active class to the current index
			}
	});
});


//End Search Recipes dropdown