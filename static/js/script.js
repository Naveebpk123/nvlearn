const logo = document.getElementById('logo');

const flashContainer = document.getElementById('flashContainer');
const flashCloseBtn = document.getElementById('flashCloseBtn');

function toggleSidebar() {
  document.getElementById("sidebar").classList.toggle("close");
  document.getElementById('contentWrapper').classList.toggle("sidebar-open");
}
logo.addEventListener('click',toggleSidebar);

flashCloseBtn.addEventListener('click',()=>{
  flashContainer.style.display = 'none';
});
