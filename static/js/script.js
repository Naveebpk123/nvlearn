const logo = document.getElementById('logo');

function toggleSidebar() {
  document.getElementById("sidebar").classList.toggle("close");
  document.getElementById('contentWrapper').classList.toggle("sidebar-open");
}
logo.addEventListener('click',toggleSidebar);
