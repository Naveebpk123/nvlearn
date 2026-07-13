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
const searchResultContainer = document.getElementById('searchResultContainer');

const logoutBtn = document.getElementById('sidebarLogout');

const deleteNoteBtns = document.getElementsByClassName('delete-note-btn');

const chatInput = document.getElementById('user-input');
const userInputContainer = document.getElementById('userInputContainer');

const readNoteContent = document.getElementsByClassName('read-note-content');

const notes = document.getElementsByClassName('note');

window.addEventListener('keydown', (e) => {
  let activeModal = null;
  if (modalBackground.style.display === 'flex') {
    activeModal = modalBackground;
  } else if (searchModalBg.style.display === 'flex') {
    activeModal = searchModalBg;
  }

  if (!activeModal) return;

  if (e.key === 'Tab' || e.keyCode === 9) {
    const focusableSelectors = 'a[href], area[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), iframe, object, embed, [tabindex="0"], [contenteditable]';
    const focusableElements = activeModal.querySelectorAll(focusableSelectors);
    
    if (focusableElements.length === 0) return;

    const firstEl = focusableElements[0];
    const lastEl = focusableElements[focusableElements.length - 1];

    if (e.shiftKey) { 
      if (document.activeElement === firstEl) {
        lastEl.focus(); 
        e.preventDefault();
      }
    } else {
      if (document.activeElement === lastEl) {
        firstEl.focus(); 
        e.preventDefault();
      }
    }
  }
});

if (notes !== null){
  for(const note of notes){
    const id = note.dataset.id;
    if (id!=='_'){
    note.addEventListener('click',()=>window.location.href = `/read_note/${id}`);
  }else{
    continue
  };
  };
};

  function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("close");
    document.getElementById('contentWrapper').classList.toggle("sidebar-open");
  }

function openModal(text, confirmBtnLink, modal) {
  const targetModal = modal || modalBackground; 
  
  targetModal.style.display = 'flex';
  
  if (text !== null && modalText) {
    modalText.innerText = text;
  }
  if (confirmBtnLink !== null && modalConfirmBtn) {
    modalConfirmBtn.setAttribute('href', confirmBtnLink);
  }
}

async function fetchSearchResults(query) {
  try {
    const response = await fetch(`/search/${query}`);
    const results = await response.json();
    console.log('Search results:', results);
    searchResultContainer.innerHTML = '';
    let htmlContent = '';
    for (const result of results.results) {
      htmlContent += `<a href="/edit/${result.id}" class="search-result">${result.title}</a>`;
    }
    searchResultContainer.innerHTML = htmlContent;
  } catch (error) {
    console.error('Error fetching search results:', error);
  }
};

logo?.addEventListener('click',toggleSidebar);

  logoutBtn?.addEventListener('click',(e)=>{
    e.preventDefault();
    openModal('Are you sure you want to logout?','/logout',modalBackground);

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
  modalSearchBar.classList.add('active');
  modalSearchBar.focus();
  searchBar.classList.add('hidden');
});

searchModalBg?.addEventListener('click',(e)=>{
  if(e.target === searchModalBg){
    searchModalBg.style.display = 'none';
    modalSearchBar.classList.remove('active');
    searchBar.classList.remove('hidden');
  }
});

modalSearchBar?.addEventListener('input',(e)=>{
  const query = e.target.value.trim();
  if(query.length > 0){
    searchBar.value = query;
  }
  fetchSearchResults(query);
});

modalSearchBar?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const query = e.target.value.trim();
    if (query) {
      window.location.href = `/search-results/${encodeURIComponent(query)}`;
    }
  }
});

chatInput?.addEventListener('input', function(){
  this.style.height = 'auto';
  this.style.height = (this.scrollHeight) + 'px';
});

chatInput?.addEventListener('keydown', async function(e){
  if(e.key === 'Enter' && !e.shiftKey){
  e.preventDefault();  
  const inputText = chatInput.value.trim();
  if(inputText.length === 0) return;

  const userBubble = document.createElement('div');
  const userBubbleText = document.createElement('p');
  userBubble.classList.add('user-bubble');
  userBubbleText.textContent = inputText;
  userBubble.appendChild(userBubbleText);
  userInputContainer.insertAdjacentElement('beforebegin', userBubble);
  const pastBubbles = Array.from(document.querySelectorAll('.user-bubble, .ai-bubble')); 
  let messageHistory=[];
  if(pastBubbles.length > 0) {
    const past8Bubbles = pastBubbles.slice(-8);
  for (const bubble of past8Bubbles) {
    if(bubble.classList.contains('user-bubble')){
      messageHistory.push({ role: 'user', contents: bubble.textContent });
    }else{
      messageHistory.push({ role: 'assistant', contents: bubble.textContent });
    }
  }};
  chatInput.value = '';
  chatInput.disabled=true;
  const response = await fetch('/ai-response', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({contents: messageHistory })
  });
  const aiResponse = await response.json();
  const aiBubble = document.createElement('div');
  aiBubble.classList.add('ai-bubble');
  aiBubble.innerHTML = aiResponse.reply;
  userInputContainer.insertAdjacentElement('beforebegin', aiBubble);
  if (window.MathJax && typeof window.MathJax.typesetPromise === 'function') {
      MathJax.typesetPromise([aiBubble]).catch((err) => console.log("MathJax error:", err.message));
    }
  chatInput.disabled=false;
  chatInput.focus();
}});

document.addEventListener('DOMContentLoaded',()=>{
  if (window.MathJax && typeof window.MathJax.typesetPromise === 'function') {
      MathJax.typesetPromise([readNoteContent]).catch((err) => console.log("MathJax error:", err.message));
    }
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




