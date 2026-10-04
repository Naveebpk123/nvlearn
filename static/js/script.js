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

const quizPreviousAttemptsBtns = document.getElementsByClassName('quizPreviousAttemptsBtn');
const previousAttemptsModalBackground = document.getElementById('previousAttemptsModalBackground');
const modalClosePreviousAttemptsBtn = document.getElementById('closePreviousAttemptsModal');
const avgScoreElement = document.getElementById('avgScore');
const avgCorrectElement = document.getElementById('avgCorrect');
const avgIncorrectElement = document.getElementById('avgIncorrect');
const avgUnansweredElement = document.getElementById('avgUnanswered');
const previousAttemptsList = document.getElementById('previousAttemptsList');
const analyticsSection = document.getElementById('analytics-section');

const noteViewOptionsBtn = document.getElementById('note-view-options-btn');
const noteViewOptions = document.getElementById('view-options-menu');
const sortBtn = document.getElementById('sort-notes');
const sortMenu = document.getElementById('sort-menu');
const sortOptions = document.querySelectorAll('#sort-menu li');
const filterBtn = document.getElementById('filter-notes');
const filterMenu = document.getElementById('filter-menu');
const filterTagOptions = document.querySelectorAll('.filter-tag-option');
const moreFilterTags = document.getElementById('more-filter-tags');

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
                window.location.href = `/edit/${id}`
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

    let newConfirmBtn;
    let newCancelBtn;
    if (modalConfirmBtn && modalCancelBtn) {
        // Clone buttons to strip all previous event listeners
        newConfirmBtn = modalConfirmBtn.cloneNode(true);
        newCancelBtn = modalCancelBtn.cloneNode(true);
        modalConfirmBtn.replaceWith(newConfirmBtn);
        modalCancelBtn.replaceWith(newCancelBtn);

        newCancelBtn.addEventListener('click', () => {
            targetModal.style.display = 'none';
        });
    }

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
        if (!searchResultContainer) return;
        if (!query) {
            searchResultContainer.innerHTML = '';
            return;
        }
        const response = await fetch(`/search/${encodeURIComponent(query)}`);
        const results = await response.json();
        searchResultContainer.innerHTML = '';
        let htmlContent = '';
        if (results && results.results) {
            for (const result of results.results) {
                htmlContent += `<a href="/edit/${result.id}" class="search-result">${result.title}</a>`;
            }
        }
        searchResultContainer.innerHTML = htmlContent;
    } catch (error) {
        return;
    }
};

searchBar?.addEventListener('click', () => {
    openModal(null, searchModalBg);
    modalSearchBar?.classList.add('active');
    modalSearchBar?.focus();
    searchBar?.classList.add('hidden');
});

searchModalBg?.addEventListener('click', (e) => {
    if (e.target === searchModalBg) {
        searchModalBg.style.display = 'none';
        modalSearchBar?.classList.remove('active');
        searchBar?.classList.remove('hidden');
        if (searchBar) searchBar.value = '';
        if (modalSearchBar) modalSearchBar.value = '';
    }
});

modalSearchBar?.addEventListener('input', (e) => {
    const query = e.target.value.trim();
    if (query.length > 0 && searchBar) {
        searchBar.value = query;
    }
    fetchSearchResults(query);
});

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
        analyticsSection?.classList.remove('hidden');
    });
}

if (quizPreviousAttemptsBtns && quizPreviousAttemptsBtns.length > 0) {
  Array.from(quizPreviousAttemptsBtns).forEach(btn => {
    btn.addEventListener('click', async () => {
      previousAttemptsModalBackground.style.display = 'flex';
      const quizId = btn.dataset.quizId;
      
      const response = await fetch(`/quiz-attempts/${quizId}`);
      const response_json = await response.json();
      
      previousAttemptsList.innerHTML = '';

      if (response_json.attempts && response_json.attempts.length > 0) {
        if (avgScoreElement) avgScoreElement.textContent = `${response_json.averages.average_percentage.toFixed(2)}%`;
        if (avgCorrectElement) avgCorrectElement.textContent = response_json.averages.average_correct.toFixed(2);
        if (avgIncorrectElement) avgIncorrectElement.textContent = response_json.averages.average_incorrect.toFixed(2);
        if (avgUnansweredElement) avgUnansweredElement.textContent = response_json.averages.average_unanswered.toFixed(2);

        const fields = [
            { 
              type: 'correct', 
              label: 'Correct', 
              value: (a) => {
                const total = a.total_questions || (a.correct_answers + a.incorrect_answers + a.unanswered);
                const pct = total > 0 ? Math.round((a.correct_answers * 100) / total) : 0;
                return `${a.correct_answers}/${total} (${pct}%)`;
              } 
            },
            { 
              type: 'incorrect', 
              label: 'Wrong', 
              value: (a) => {
                const total = a.total_questions || (a.correct_answers + a.incorrect_answers + a.unanswered);
                const pct = total > 0 ? Math.round((a.incorrect_answers * 100) / total) : 0;
                return `${a.incorrect_answers}/${total} (${pct}%)`;
              } 
            },
            { 
              type: 'unanswered', 
              label: 'Unanswered', 
              value: (a) => {
                const total = a.total_questions || (a.correct_answers + a.incorrect_answers + a.unanswered);
                const pct = total > 0 ? Math.round((a.unanswered * 100) / total) : 0;
                return `${a.unanswered}/${total} (${pct}%)`;
              } 
            }
        ];

        for (const attempt of response_json.attempts) {
            const statsHtml = fields.map(field => `
              <div class="stat-item ${field.type}">
                <span class="stat-value">${field.value(attempt)}</span>
                <span class="stat-label">${field.label}</span>
              </div>
            `).join('');

            const attemptBar = document.createElement('div');
            attemptBar.className = 'previous-attempt';
            attemptBar.innerHTML = statsHtml;
            previousAttemptsList.appendChild(attemptBar);
        }
      } else if (response_json.error) {
        flash(response_json.error, 'error');
      } else {
        previousAttemptsList.innerHTML = '<p class="empty-msg">No attempts yet.</p>';
      }
    });
  });
}


if (modalClosePreviousAttemptsBtn) {
    modalClosePreviousAttemptsBtn.addEventListener('click', () => {
        previousAttemptsModalBackground.style.display = 'none';
    });}

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
        analyticsSection?.classList.add('hidden');
    });
}

if (quizzesTab) {
    quizzesTab.addEventListener('click', () => {
        tabcontainer.classList.add('hidden');
        quizzesContent?.classList.remove('hidden');
        backBtn.classList.remove('hidden');
        analyticsSection?.classList.add('hidden');
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
        btn?.addEventListener('click', async function(e) {
            e.preventDefault();
            const response = await fetch(`/move_to_bin/${btn.dataset.noteId}`, {
                method: 'POST'
            });
            const response_json = await response.json();
            flash(response_json[0], response_json[1]);
            btn.closest('.note').remove();
        })
    }
}

if (noteViewOptionsBtn) {
    noteViewOptionsBtn.addEventListener('click', () => {
        noteViewOptions.classList.toggle('hidden');
    });
}

if(sortBtn){
    sortBtn.addEventListener('click',()=>{
        noteViewOptions.classList.toggle('hidden')
        sortMenu.classList.toggle('hidden')
    })
}

if (filterBtn) {
    filterBtn.addEventListener('click', () => {
        noteViewOptions.classList.add('hidden');
        filterMenu.classList.toggle('hidden');
    });
}

function applyNoteTagFilter() {
    const selectedTags = Array.from(filterMenu?.querySelectorAll('input[type="checkbox"]:checked') || [])
        .map(input => input.value.toLowerCase());

    for (const note of notes) {
        if (note.dataset.id === '_') continue;
        let noteTags = [];
        try {
            noteTags = JSON.parse(note.dataset.tags || '[]');
        } catch (error) {
            noteTags = [];
        }
        const normalizedTags = noteTags.map(tag => String(tag).toLowerCase());
        const matches = selectedTags.length === 0 || selectedTags.some(tag => normalizedTags.includes(tag));
        note.classList.toggle('filtered-note', !matches);
    }
}

filterTagOptions.forEach(option => {
    option.querySelector('input')?.addEventListener('change', applyNoteTagFilter);
});

moreFilterTags?.addEventListener('click', () => {
    filterMenu.querySelectorAll('.extra-filter-tag').forEach(option => option.classList.remove('hidden'));
    moreFilterTags.remove();
});

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
    if (filterMenu && !filterMenu.contains(e.target) && e.target !== filterBtn) {
        filterMenu.classList.add('hidden');
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
        aiBubble.innerHTML = `${aiResponse.chat || ''}<br>${aiResponse.note_action || ''}<br>${aiResponse.notes || ''}`;        
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

/**
 * Dark Mode & Theme Switcher Controller
 * Supports 'light', 'dark', and 'system' options with localStorage persistence and OS media query listener.
 */
const themeIcons = {
    light: `<svg class="theme-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`,
    dark: `<svg class="theme-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`,
    system: `<svg class="theme-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>`
};

const themeLabels = {
    light: 'Light',
    dark: 'Dark',
    system: 'System'
};

function applyTheme(theme) {
    const root = document.documentElement;
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    let isDark = false;
    if (theme === 'dark') {
        isDark = true;
    } else if (theme === 'light') {
        isDark = false;
    } else {
        isDark = systemPrefersDark;
    }

    if (isDark) {
        root.classList.add('dark');
    } else {
        root.classList.remove('dark');
    }

    const themeBtnIcon = document.getElementById('themeBtnIcon');
    const themeBtnText = document.getElementById('themeBtnText');
    const themeOptionsList = document.querySelectorAll('.theme-option');

    if (themeBtnIcon) themeBtnIcon.innerHTML = themeIcons[theme] || themeIcons.system;
    if (themeBtnText) themeBtnText.textContent = themeLabels[theme] || 'System';

    themeOptionsList.forEach(opt => {
        if (opt.dataset.theme === theme) {
            opt.classList.add('active');
        } else {
            opt.classList.remove('active');
        }
    });
}

function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'system';
    applyTheme(savedTheme);

    const themeDropdownWrapper = document.getElementById('themeDropdownWrapper');
    const themeDropdownBtn = document.getElementById('themeDropdownBtn');
    const themeDropdownMenu = document.getElementById('themeDropdownMenu');
    const themeOptionsList = document.querySelectorAll('.theme-option');

    if (themeDropdownBtn && themeDropdownMenu) {
        themeDropdownBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = themeDropdownMenu.classList.contains('hidden');
            if (isHidden) {
                themeDropdownMenu.classList.remove('hidden');
                themeDropdownWrapper?.classList.add('open');
            } else {
                themeDropdownMenu.classList.add('hidden');
                themeDropdownWrapper?.classList.remove('open');
            }
        });

        themeOptionsList.forEach(opt => {
            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                const selectedTheme = opt.dataset.theme;
                localStorage.setItem('theme', selectedTheme);
                applyTheme(selectedTheme);
                themeDropdownMenu.classList.add('hidden');
                themeDropdownWrapper?.classList.remove('open');
            });
        });

        document.addEventListener('click', (e) => {
            if (themeDropdownWrapper && !themeDropdownWrapper.contains(e.target)) {
                themeDropdownMenu.classList.add('hidden');
                themeDropdownWrapper.classList.remove('open');
            }
        });
    }

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        const currentTheme = localStorage.getItem('theme') || 'system';
        if (currentTheme === 'system') {
            applyTheme('system');
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    if (readNoteContent && window.MathJax && typeof window.MathJax.typesetPromise === 'function') {
        MathJax.typesetPromise([readNoteContent]).catch(() => {});
    }
});
