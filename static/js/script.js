const logo = document.getElementById('logo');

const flashContainer = document.getElementById('flashContainer');
const flashCloseBtn = document.getElementById('flashCloseBtn');

const modalBackground = document.getElementById('modalBackground'); //This is also container for the modal
const modalText = document.getElementById('modalText');
const modalCancelBtn = document.getElementById('modalCancelBtn');
const modalConfirmBtn = document.getElementById('modalConfirmBtn');

const searchBar = document.getElementById('searchBar');
const searchModalBg = document.getElementById('searchModalBackground');
const modalSearchBar = document.getElementById('modalSearchBar');

const logoutBtn = document.getElementById('sidebarLogout');

const deleteNoteBtns = document.getElementsByClassName('delete-note-btn');

const focusableElements = [modalConfirmBtn, modalCancelBtn];
const firstFocusableElement = focusableElements[0];
const lastFocusableElement = focusableElements[focusableElements.length - 1];

window.addEventListener('keydown',(e)=> {
  if (modalBackground.style.display === 'flex' || searchModalBg.style.display === 'flex') {
    
    if (e.key === 'Tab' || e.keyCode === 9) {
      
      if (e.shiftKey) { 
        if (document.activeElement === firstFocusableElement) {
          lastFocusableElement.focus(); 
          e.preventDefault();
        }
      } else {
        if (document.activeElement === lastFocusableElement) {
          firstFocusableElement.focus(); 
          e.preventDefault();
        }
      }
      
    }
  }
});

  function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("close");
    document.getElementById('contentWrapper').classList.toggle("sidebar-open");
  }

  function openModal(text,confirmBtnLink,modal){
    modal.style.display = 'flex';
    if(text !== null){
    modalText.innerText = text;
  };
   if(confirmBtnLink !== null){
     modalConfirmBtn.setAttribute('href',confirmBtnLink);
   };
  }

  logo?.addEventListener('click',toggleSidebar);

  logoutBtn?.addEventListener('click',(e)=>{
    e.preventDefault();
    openModal('Are you sure you want to logout?','/logout');

  });
if(deleteNoteBtns !== null){
for (const btn of deleteNoteBtns){
  btn?.addEventListener('click',(e)=>{
    e.preventDefault();
    openModal('Are you sure you want to permanently delete this note?',btn.dataset.link,modalBackground);
  })};
};

searchBar?.addEventListener('click',()=> {
  openModal(null,null,searchModalBg);
});

modalConfirmBtn?.addEventListener('click',()=>{
  modalBackground.style.display = 'none';
});
modalCancelBtn?.addEventListener('click',()=>{
  modalBackground.style.display = 'none';
  modalConfirmBtn.setAttribute('href','');
});

flashCloseBtn?.addEventListener('click',()=>{
  flashContainer.style.display = 'none';
});




