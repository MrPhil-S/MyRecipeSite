// Get radio buttons and sections
const individualRadio = document.getElementById('individualMethod');
const bulkRadio = document.getElementById('bulkMethod');
const individualSection = document.getElementById('individualIngredients');
const bulkSection = document.getElementById('bulkAdd');

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
