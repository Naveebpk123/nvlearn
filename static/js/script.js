const logo = document.getElementById('logo');

const notificationBar = document.getElementById('notificationBar');

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

const moveToBinBtns = document.getElementsByClassName('move-to-bin');
const restoreBtns = document.getElementsByClassName('restore-btn');

const chatInput = document.getElementById('user-input');
const userInputContainer = document.getElementById('userInputContainer');

const readNoteContent = document.getElementById('read-note-content');

const notes = document.getElementsByClassName('note');

async function flash(text='',category='success'){
  const flashAlert = document.createElement('div');
  flashAlert.classList.add('alert',`alert-${category}`);
  const flashMsg = document.createElement('span');
  flashMsg.innerText = text;
  const flashCloseBtn = document.createElement('button');
  flashCloseBtn.classList.add('flashCloseBtn');
  flashCloseBtn.innerText = 'X';
  flashCloseBtn.addEventListener('click',()=>{
    flashAlert.remove();
  })
  notificationBar.appendChild(flashAlert);
  flashAlert.appendChild(flashMsg);
  flashAlert.appendChild(flashCloseBtn);
  setTimeout(()=> flashAlert.remove(), 3000);
}

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
    note.addEventListener('click',(e)=>{
      if(e.target.closest('.action-buttons')){
        return;
      };
      window.location.href = `/read_note/${id}`
    });
  }else{
    continue
  };
  };
};

  function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("close");
    document.getElementById('contentWrapper').classList.toggle("sidebar-open");
  }

function openModal(text, modal, action = null, note_id = null, triggerBtn = null) {
  const targetModal = modal || modalBackground; 
  
  targetModal.style.display = 'flex';
  
  if (text !== null && modalText) {
    modalText.innerText = text;
  }
  const newConfirmBtn = modalConfirmBtn.cloneNode(true);
  const newCancelBtn = modalCancelBtn.cloneNode(true);
  modalConfirmBtn.replaceWith(newConfirmBtn);
  modalCancelBtn.replaceWith(newCancelBtn);

  newCancelBtn.addEventListener('click', () => {
    targetModal.style.display = 'none';
  });

  if (action) {
    newConfirmBtn.addEventListener('click', async function() {
      if (action === 'delete-note') { 
        const response = await fetch(`/delete/${note_id}`, { method: 'POST' });
        const response_json = await response.json();
        targetModal.style.display = 'none';
        flash(response_json[0], response_json[1]);
        
        if (response_json[1] === 'success' && triggerBtn) {
          triggerBtn.closest('.note').remove();
        }
      } 
      else if (action === 'logout') {
        const response = await fetch('/logout', { method: 'POST' });
        const response_json = await response.json();
        if (response_json[1] === 'success') {
          window.location.href = '/';
        } else {
          targetModal.style.display = 'none';
          flash(response_json[0],response_json[1])
        }
      }      
    });
  }
}

async function fetchSearchResults(query) {
  try {
     if (!query) {
    searchResultContainer.innerHTML = '';
    return;
  }
    let results;
    if (query){
    const response = await fetch(`/search/${encodeURIComponent(query)}`);
    results = await response.json();
    }
    searchResultContainer.innerHTML = '';
    let htmlContent = '';
    for (const result of results.results) {
      htmlContent += `<a href="/edit/${result.id}" class="search-result">${result.title}</a>`;
    }
    searchResultContainer.innerHTML = htmlContent;
  } catch (error) {
    console.log('An error occured while fetching search results')
  }
};

logo?.addEventListener('click',toggleSidebar);

logoutBtn?.addEventListener('click', (e) => {
  e.preventDefault();
  openModal('Are you sure you want to logout?', modalBackground, 'logout');
});

if (deleteNoteBtns !== null) {
  for (const btn of deleteNoteBtns) {
    btn?.addEventListener('click', (e) => {
      e.preventDefault();
      openModal(
        'Are you sure you want to permanently delete this note?', 
        modalBackground, 
        'delete-note', 
        btn.dataset.noteId, 
        btn
      );
    });
  }
}


if(moveToBinBtns){
  for(const btn of moveToBinBtns){
    btn?.addEventListener('click',async function(){
      const response = await fetch(`/move_to_bin/${btn.dataset.noteId}`,{method:'POST'});
      const response_json = await response.json();
      flash(response_json[0],response_json[1]);
      btn.closest('.note').remove();
    })
  }
}

if(restoreBtns){
  for(const btn of restoreBtns){
    btn?.addEventListener('click',async function(){
      const response = await fetch(`/restore/${btn.dataset.noteId}`,{method:'POST'});
      const response_json = await response.json();
      flash(response_json[0],response_json[1]);
      btn.closest('.note').remove();
    })
  }
}


searchBar?.addEventListener('click',()=> {
  openModal(null,searchModalBg);
  modalSearchBar.classList.add('active');
  modalSearchBar.focus();
  searchBar.classList.add('hidden');
});

searchModalBg?.addEventListener('click',(e)=>{
  if(e.target === searchModalBg){
    searchModalBg.style.display = 'none';
    modalSearchBar.classList.remove('active');
    searchBar.classList.remove('hidden');
    searchBar.value = '';
    modalSearchBar.value = '';
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
  chatInput.style.height = 'auto';
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
  aiBubble.innerHTML = `${aiResponse.chat || ''} \n ${aiResponse.note_action || ''} \n ${aiResponse.notes || ''}`;
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






