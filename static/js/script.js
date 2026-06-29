const logo = document.getElementById('logo');

const flashContainer = document.getElementById('flashContainer');
const flashCloseBtn = document.getElementById('flashCloseBtn');

const modalBackground = document.getElementById('modalBackground'); //This is also container for the modal
const modalText = document.getElementById('modalText');
const modalCancelBtn = document.getElementById('modalCancelBtn');
const modalConfirmBtn = document.getElementById('modalConfirmBtn');

const logoutBtn = document.getElementById('sidebarLogout');

function toggleSidebar() {
  document.getElementById("sidebar").classList.toggle("close");
  document.getElementById('contentWrapper').classList.toggle("sidebar-open");
}
logo.addEventListener('click',toggleSidebar);

logoutBtn.addEventListener('click',(e)=>{
  e.preventDefault();
  modalBackground.style.display = 'flex';
  modalText.innerText = 'Are you sure you want to logout?';
  modalConfirmBtn.setAttribute('href','/logout');
});

modalConfirmBtn.addEventListener('click',()=>{
  modalBackground.style.display = 'none';
});
modalCancelBtn.addEventListener('click',()=>{
  modalBackground.style.display = 'none';
  modalConfirmBtn.setAttribute('href','');
});

flashCloseBtn.addEventListener('click',()=>{
  flashContainer.style.display = 'none';
});


