// DOM Element Selectors
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
const noteContainer = document.getElementsByClassName('note-container')[0];

const flashcards = document.getElementsByClassName('flashcard');
const nextBtn = document.getElementById('nextButton');
const previousBtn = document.getElementById('previousButton');
const saveFlashcardsBtn = document.getElementById('saveFlashcardsBtn');
const innerFlashcardContainer = document.querySelector('.inner-flashcard-container');
const deleteFlashcardsBtn = document.getElementsByClassName('delete-flashcard-btn');

const flashcardsTab = document.getElementById('flashcardsTab');
const quizzesTab = document.getElementById('quizzesTab');
const flashcardsContent = document.getElementById('flashcardsContent');
const quizzesContent = document.getElementById('quizzesContent');
const tabcontainer = document.getElementsByClassName('tab-container')[0];
const backBtn = document.getElementById('backBtn');
const deleteQuizBtns = document.getElementsByClassName('delete-quiz-btn');

const sortBtn = document.getElementById('sort-btn');
const sortMenu = document.getElementById('sort-menu');
const sortOptions = document.querySelectorAll('#sort-menu li');

/**
 * Creates and displays a dynamic floating notification alert.
 * Auto-dismisses after 3 seconds or on close button click.
 * @param {string} text - Message text to display.
 * @param {string} category - Alert category ('success', 'error', 'info').
 */
async function flash(text = '', category = 'success') {
    const flashAlert = document.createElement('div');
    flashAlert.classList.add('alert', `alert-${category}`);
    const flashMsg = document.createElement('span');
    flashMsg.innerText = text;
    const flashCloseBtn = document.createElement('button');
    flashCloseBtn.classList.add('flashCloseBtn');
    flashCloseBtn.innerText = 'X';
    flashCloseBtn.addEventListener('click', () => {
        flashAlert.remove();
    })
    notificationBar.appendChild(flashAlert);
    flashAlert.appendChild(flashMsg);
    flashAlert.appendChild(flashCloseBtn);
    setTimeout(() => flashAlert.remove(), 3000);
}

/**
 * Focus Trap Accessibility Listener:
 * Intercepts Tab and Shift+Tab key presses when a modal is active to lock keyboard focus inside the modal dialog.
 */
window.addEventListener('keydown', (e) => {
    let activeModal = null;
    if (modalBackground && modalBackground.style.display === 'flex') {
        activeModal = modalBackground;
    } else if (searchModalBg && searchModalBg.style.display === 'flex') {
        activeModal = searchModalBg;
    }

    if (!activeModal) return;

    if (e.key === 'Tab') {
        const focusableSelectors = 'a[href], area[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), iframe, object, embed, [tabindex="0"], [contenteditable]';
        const focusableElements = activeModal.querySelectorAll(focusableSelectors);

        if (focusableElements.length === 0) return;

        const firstEl = focusableElements[0];
        const lastEl = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) { // Shift + Tab: Move focus to last element if currently on first
            if (document.activeElement === firstEl) {
                lastEl.focus();
                e.preventDefault();
            }
        } else { // Tab: Move focus to first element if currently on last
            if (document.activeElement === lastEl) {
                firstEl.focus();
                e.preventDefault();
            }
        }
    }
});

if (notes !== null) {
    for (const note of notes) {
        const id = note.dataset.id;
        if (id !== '_') {
            note.addEventListener('click', (e) => {
                if (e.target.closest('.action-buttons')) {
                    return;
                };
                window.location.href = `/read_note/${id}`
            });
        } else {
            continue
        };
    };
};

function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("close");
    document.getElementById('contentWrapper').classList.toggle("sidebar-open");
}

/**
 * Opens a modal popup with confirmation handlers.
 * Replaces button nodes via cloneNode(true) to clear previous event listeners before binding new AJAX actions.
 * @param {string|null} text - Message text to display inside modal.
 * @param {HTMLElement} modal - Target modal container element.
 * @param {string|null} action - Action identifier ('delete-note', 'logout', 'delete-flashcards', 'delete-quiz').
 * @param {string|null} id - Target resource ID for deletion/action.
 * @param {HTMLElement|null} triggerBtn - Button element that triggered the modal.
 */
function openModal(text, modal, action = null, id = null, triggerBtn = null) {
    const targetModal = modal || modalBackground;

    targetModal.style.display = 'flex';

    if (text !== null && modalText) {
        modalText.innerText = text;
    }

    // Clone buttons to strip all previous event listeners
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
                const response = await fetch(`/delete/${id}`, {
                    method: 'POST'
                });
                const response_json = await response.json();
                targetModal.style.display = 'none';
                flash(response_json[0], response_json[1]);

                if (response_json[1] === 'success' && triggerBtn) {
                    triggerBtn.closest('.note').remove();
                }
            } else if (action === 'logout') {
                const response = await fetch('/logout', {
                    method: 'POST'
                });
                const response_json = await response.json();
                if (response_json[1] === 'success') {
                    window.location.href = '/';
                }
            } else if (action === 'delete-flashcards') {
                const response = await fetch(`/delete-flashcards/${id}`, {
                    method: 'POST'
                });
                const response_json = await response.json();
                targetModal.style.display = 'none';
                flash(response_json[0], response_json[1]);
                if (response_json[1] === 'success' && triggerBtn) {
                    triggerBtn.closest('.flashcard-set').remove();
                }
            } else if (action === 'delete-quiz') {
                const response = await fetch(`/delete-quiz/${id}`, {
                    method: 'POST'
                });
                const response_json = await response.json();
                if (response_json[1] === 'success' && triggerBtn) {
                    triggerBtn.closest('.quiz-card').remove();
                };
                targetModal.style.display = 'none';
                flash(response_json[0], response_json[1]);
            }
        });
    }
}

/**
 * Live Search API Client:
 * Fetches matching note titles from /search/<query> and populates searchResultContainer.
 * @param {string} query - User search query text.
 */
async function fetchSearchResults(query) {
    try {
        if (!query) {
            searchResultContainer.innerHTML = '';
            return;
        }
        let results;
        if (query) {
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
        return;
    }
};

logo?.addEventListener('click', toggleSidebar);

/**
 * 3D Flashcard Deck Controller:
 * Manages active card index, updates translateX transform offset (-index * 100%), and toggles next/prev buttons.
 */
if (flashcards && flashcards.length > 0) {
    let currentCardIndex = 0;
    const initialCurrentIndex = Array.from(flashcards).findIndex(card => card.classList.contains('current'));
    if (initialCurrentIndex !== -1) {
        currentCardIndex = initialCurrentIndex;
    }

    function updateFlashcardPosition() {
        if (currentCardIndex < 0) currentCardIndex = 0;
        if (currentCardIndex >= flashcards.length) currentCardIndex = flashcards.length - 1;

        Array.from(flashcards).forEach((card, idx) => {
            card.classList.remove('flipped');
            if (idx === currentCardIndex) {
                card.classList.add('current');
            } else {
                card.classList.remove('current');
            }
        });

        // Slide flashcard container track horizontally
        if (innerFlashcardContainer) {
            innerFlashcardContainer.style.transform = `translateX(-${currentCardIndex * 100}%)`;
        }

        if (previousBtn) {
            previousBtn.disabled = (currentCardIndex === 0);
        }
        if (nextBtn) {
            nextBtn.disabled = (currentCardIndex >= flashcards.length - 1);
        }
    }

    updateFlashcardPosition();

    // Toggle 3D card flip on click
    Array.from(flashcards).forEach(flashcard => {
        flashcard.addEventListener('click', () => {
            flashcard.classList.toggle('flipped');
        });
    });

    if (nextBtn) {
        nextBtn.addEventListener('click', () => {
            if (currentCardIndex < flashcards.length - 1) {
                currentCardIndex++;
                updateFlashcardPosition();
            }
        });
    }

    if (previousBtn) {
        previousBtn.addEventListener('click', () => {
            if (currentCardIndex > 0) {
                currentCardIndex--;
                updateFlashcardPosition();
            }
        });
    }
}

if (backBtn) {
    backBtn.addEventListener('click', () => {
        tabcontainer.classList.remove('hidden');
        flashcardsContent?.classList.add('hidden');
        quizzesContent?.classList.add('hidden');
        backBtn.classList.add('hidden');
    });
}

logoutBtn?.addEventListener('click', (e) => {
    e.preventDefault();
    openModal('Are you sure you want to logout?', modalBackground, 'logout');
});

if (deleteQuizBtns !== null) {
    for (const btn of deleteQuizBtns) {
        btn?.addEventListener('click', (e) => {
            e.preventDefault();
            openModal(
                'Are you sure you want to permanently delete this quiz?',
                modalBackground,
                'delete-quiz',
                btn.dataset.quizId,
                btn
            );
        });
    }
}

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

if (deleteFlashcardsBtn !== null) {
    for (const btn of deleteFlashcardsBtn) {
        btn?.addEventListener('click', (e) => {
            e.preventDefault();
            openModal(
                'Are you sure you want to permanently delete this flashcard set?',
                modalBackground,
                'delete-flashcards',
                btn.dataset.flashcardId,
                btn
            );
        });
    }
};

if (flashcardsTab) {
    flashcardsTab.addEventListener('click', () => {
        tabcontainer.classList.add('hidden');
        flashcardsContent.classList.remove('hidden');
        backBtn.classList.remove('hidden');
    });
}

if (quizzesTab) {
    quizzesTab.addEventListener('click', () => {
        tabcontainer.classList.add('hidden');
        quizzesContent?.classList.remove('hidden');
        backBtn.classList.remove('hidden');
    });
}

if (saveFlashcardsBtn) {
    saveFlashcardsBtn.addEventListener('click', async function() {
        const response = await fetch(`/save-flashcards/${saveFlashcardsBtn.dataset.id}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        const responseJSON = await response.json();
        if (responseJSON.status == 'saved') {
            saveFlashcardsBtn.disabled = true;
            flash('Saved flashcards', 'success');
        } else {
            flash('Unable to save', 'error')
        };
    });
};

if (moveToBinBtns) {
    for (const btn of moveToBinBtns) {
        btn?.addEventListener('click', async function() {
            const response = await fetch(`/move_to_bin/${btn.dataset.noteId}`, {
                method: 'POST'
            });
            const response_json = await response.json();
            flash(response_json[0], response_json[1]);
            btn.closest('.note').remove();
        })
    }
}

if (sortBtn) {
    sortBtn.addEventListener('click', () => {
        sortMenu.classList.toggle('hidden');
    });
}

/**
 * Note Sorting Algorithm:
 * Sorts DOM note elements in-place by title (A-Z, Z-A) or timestamp (last opened / least recently opened).
 */
if (sortOptions) {
    for (const option of sortOptions) {
        option.addEventListener('click', async function() {
            const sortType = option.dataset.sort;
            if (sortType === 'az') {
                const sortedNotes = Array.from(notes).sort((a, b) => a.querySelector(".note-title").textContent.localeCompare(b.querySelector(".note-title").textContent));
                for (const note of sortedNotes) {
                    noteContainer.appendChild(note);
                }
            } else if (sortType === 'za') {
                const sortedNotes = Array.from(notes).sort((a, b) => b.querySelector(".note-title").textContent.localeCompare(a.querySelector(".note-title").textContent));
                for (const note of sortedNotes) {
                    noteContainer.appendChild(note);
                }
            } else if (sortType === 'last-opened') {
                const sortedNotes = Array.from(notes).sort((a, b) => {
                    const lastOpenedA = new Date(a.dataset.lastOpened);
                    const lastOpenedB = new Date(b.dataset.lastOpened);
                    return lastOpenedB - lastOpenedA;
                });
                for (const note of sortedNotes) {
                    noteContainer.appendChild(note);
                }
            } else if (sortType === 'least-recently-opened') {
                const sortedNotes = Array.from(notes).sort((a, b) => {
                    const lastOpenedA = new Date(a.dataset.lastOpened);
                    const lastOpenedB = new Date(b.dataset.lastOpened);
                    return lastOpenedA - lastOpenedB;
                });
                for (const note of sortedNotes) {
                    noteContainer.appendChild(note);
                }
            }
        })
    }
}

document.addEventListener('click', (e) => {
    if (sortMenu && !sortMenu.contains(e.target) && e.target !== sortBtn) {
        sortMenu.classList.add('hidden');
    }
});

if (restoreBtns) {
    for (const btn of restoreBtns) {
        btn?.addEventListener('click', async function() {
            const response = await fetch(`/restore/${btn.dataset.noteId}`, {
                method: 'POST'
            });
            const response_json = await response.json();
            flash(response_json[0], response_json[1]);
            btn.closest('.note').remove();
        })
    }
}

searchBar?.addEventListener('click', () => {
    openModal(null, searchModalBg);
    modalSearchBar.classList.add('active');
    modalSearchBar.focus();
    searchBar.classList.add('hidden');
});

searchModalBg?.addEventListener('click', (e) => {
    if (e.target === searchModalBg) {
        searchModalBg.style.display = 'none';
        modalSearchBar.classList.remove('active');
        searchBar.classList.remove('hidden');
        searchBar.value = '';
        modalSearchBar.value = '';
    }
});

modalSearchBar?.addEventListener('input', (e) => {
    const query = e.target.value.trim();
    if (query.length > 0) {
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

chatInput?.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

/**
 * AI Chat Submission Handler:
 * Extracts last 8 conversation turns, sends message payload to /ai-response, appends AI response bubble, and triggers MathJax LaTeX typesetting.
 */
chatInput?.addEventListener('keydown', async function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const inputText = chatInput.value.trim();
        if (inputText.length === 0) return;

        const userBubble = document.createElement('div');
        const userBubbleText = document.createElement('p');
        userBubble.classList.add('user-bubble');
        userBubbleText.textContent = inputText;
        userBubble.appendChild(userBubbleText);
        userInputContainer.insertAdjacentElement('beforebegin', userBubble);
        const pastBubbles = Array.from(document.querySelectorAll('.user-bubble, .ai-bubble'));
        let messageHistory = [];
        if (pastBubbles.length > 0) {
            const past8Bubbles = pastBubbles.slice(-8); // Collect last 8 turns for AI context window
            for (const bubble of past8Bubbles) {
                if (bubble.classList.contains('user-bubble')) {
                    messageHistory.push({
                        role: 'user',
                        contents: bubble.textContent
                    });
                } else {
                    messageHistory.push({
                        role: 'assistant',
                        contents: bubble.textContent
                    });
                }
            }
        };
        chatInput.value = '';
        chatInput.style.height = 'auto';
        chatInput.disabled = true;

        const response = await fetch('/ai-response', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                contents: messageHistory
            })
        });
        const aiResponse = await response.json();
        const aiBubble = document.createElement('div');
        aiBubble.classList.add('ai-bubble');
        aiBubble.innerHTML = `${aiResponse.chat || ''} \n ${aiResponse.note_action || ''} \n ${aiResponse.notes || ''}`;
        if (aiResponse.flashcard_id) {
            const flashcardLink = document.createElement('a');
            flashcardLink.className = 'button';
            flashcardLink.href = `/flashcards/${aiResponse.flashcard_id}`;
            flashcardLink.textContent = 'View Flashcards';
            flashcardLink.target = '_blank';
            aiBubble.appendChild(flashcardLink);
        };
        if (aiResponse.quiz_id) {
            const quizLink = document.createElement('a');
            quizLink.className = 'button';
            quizLink.href = `/quiz/${aiResponse.quiz_id}`;
            quizLink.textContent = 'View Quiz';
            quizLink.target = '_blank';
            aiBubble.appendChild(quizLink);
        }
        userInputContainer.insertAdjacentElement('beforebegin', aiBubble);
        // Trigger MathJax LaTeX typesetting for generated AI mathematical equations
        if (window.MathJax && typeof window.MathJax.typesetPromise === 'function') {
            MathJax.typesetPromise([aiBubble]).catch(() => {});
        }
        chatInput.disabled = false;
        chatInput.focus();
    }
});

document.addEventListener('DOMContentLoaded', () => {
    if (readNoteContent && window.MathJax && typeof window.MathJax.typesetPromise === 'function') {
        MathJax.typesetPromise([readNoteContent]).catch(() => {});
    }
});