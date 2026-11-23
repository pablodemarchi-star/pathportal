(() => {
  document.querySelectorAll('[data-online-report-flow]').forEach(dialog => {
    const adminEdit = Boolean(dialog.closest?.('[data-admin-report-edit]'));
    const form = dialog.querySelector('[data-session-report-form]');
    const questions = form.querySelector('.staff-session-report-questions');
    const cards = Array.from(questions.children);
    const definitions = [
      ['session', 'Session', 'Confirm the session outcome and candidate attendance.'],
      ['modules', 'Exam modules', 'Verify the files for each module in this session.'],
      ['candidates', 'Candidate IT issues', 'Record any technical difficulties affecting candidates.'],
      ['team', 'Staff review', 'Evaluate each staff member, add comments where needed and complete the final checks.'],
      ['finish', 'Finish', 'Review your progress and add optional comments before submitting.'],
    ];
    const steps = definitions.filter(([key]) => cards.some(card => card.dataset.reportStage === key));
    if (!steps.length) return;
    let current = 0, locked = false;
    const make = (tag, text, className) => {
      const node = document.createElement(tag);
      if (text !== undefined) node.textContent = text;
      if (className) node.className = className;
      return node;
    };
    const header = make('header', undefined, 'report-flow-header');
    const heading = form.querySelector('.staff-session-report-heading');
    const subtitle = form.querySelector('.staff-session-report-subtitle');
    const context = form.querySelector('[data-report-session-context]');
    header.append(heading);
    if (context) header.append(context);
    if (subtitle) subtitle.hidden = true;
    const workspace = make('div', undefined, 'report-flow-workspace');
    const sidebar = make('aside', undefined, 'report-flow-sidebar');
    const progressLabel = make('p', '', 'report-flow-progress-label');
    progressLabel.setAttribute('role', 'status');
    progressLabel.setAttribute('aria-live', 'polite');
    const progress = make('progress'); progress.max = steps.length;
    progress.setAttribute('aria-label', 'Report sections ready');
    const nav = make('nav', undefined, 'report-flow-nav');
    nav.setAttribute('aria-label', 'Report sections');
    nav.style.setProperty('--report-step-count', steps.length);
    sidebar.append(progressLabel, progress, nav, make('p', 'Move between sections without losing your answers.', 'report-flow-tip'));
    const content = make('div', undefined, 'report-flow-content');
    const stageHeading = make('div', undefined, 'report-flow-stage-heading');
    const position = make('span', '', 'report-flow-position');
    const title = make('h3'); title.tabIndex = -1;
    const description = make('p');
    stageHeading.append(position, title, description);
    const warning = form.querySelector('.staff-session-report-warning');
    const summary = make('section', undefined, 'report-flow-summary');
    summary.setAttribute('aria-label', 'Report progress summary');
    const summaryTitle = make('h4', adminEdit ? 'Before you save' : 'Before you submit');
    const summaryText = make('p', adminEdit ? 'Review your changes before saving. Changes update the report and linked Attendance records and are recorded in the edit history.' : 'Check the sections below and review your answers. Once submitted, this report cannot be reopened or edited.');
    const summaryRows = make('div', undefined, 'report-flow-summary-rows');
    summary.append(summaryTitle, summaryText, summaryRows);
    content.append(stageHeading);
    if (warning) content.append(warning);
    content.append(summary, questions);
    workspace.append(sidebar, content);
    const footer = make('footer', undefined, 'report-flow-footer');
    const feedback = form.querySelector('[data-report-feedback]');
    const draft = form.querySelector('[data-report-draft-status]');
    const actions = form.querySelector('.staff-session-report-actions');
    const submit = actions.querySelector('[type="submit"]');
    const close = actions.querySelector('[data-session-report-close]');
    if (close) close.textContent = 'Close';
    const previous = make('button', 'Back', 'secondary-button'); previous.type = 'button';
    const next = make('button', 'Continue', 'primary-button'); next.type = 'button';
    previous.addEventListener('click', () => show(current - 1));
    next.addEventListener('click', () => advance());
    actions.insertBefore(previous, submit);
    actions.insertBefore(next, submit);
    const footerStatus = make('div', undefined, 'report-flow-footer-status');
    if (feedback) footerStatus.append(feedback);
    if (draft) footerStatus.append(draft);
    footer.append(footerStatus, actions);
    form.prepend(header);
    form.append(workspace, footer);
    dialog.classList.add('is-guided-online-report');
    const controls = key => cards.filter(card => !key || card.dataset.reportStage === key)
      .flatMap(card => Array.from(card.querySelectorAll('input, select, textarea')))
      .filter(input => !input.disabled && input.willValidate !== false);
    const invalid = key => {
      const radioGroups = new Set();
      return controls(key).filter(input => {
        if (input.checkValidity()) return false;
        if (input.type === 'radio') {
          if (radioGroups.has(input.name)) return false;
          radioGroups.add(input.name);
        }
        return true;
      });
    };
    const buttons = steps.map(([key, label], index) => {
      const button = make('button', undefined, 'report-flow-step'); button.type = 'button';
      const number = make('span', String(index + 1).padStart(2, '0'), 'report-flow-step-number');
      const name = make('span', label, 'report-flow-step-name');
      const state = make('span', '', 'report-flow-step-state');
      button.append(number, name, state);
      button.addEventListener('click', () => show(index));
      nav.append(button);
      return {button, number, state};
    });
    function update() {
      if (locked) { progressLabel.textContent = 'Report submitted'; return; }
      let ready = 0;
      summaryRows.replaceChildren();
      steps.forEach(([key, label], index) => {
        const pending = key === 'finish' ? invalid().length : invalid(key).length;
        const required = key === 'finish' || controls(key).some(input => input.required);
        if (!pending) ready++;
        const {button, number, state} = buttons[index];
        button.classList.toggle('is-ready', !pending);
        number.textContent = !pending ? '✓' : String(index + 1).padStart(2, '0');
        state.textContent = pending ? 'Needs attention' : required ? 'Ready' : 'Optional';
        button.setAttribute('aria-label', `${index + 1}. ${label} · ${state.textContent}`);
        if (index === steps.length - 1) return;
        const row = make('button', undefined, 'report-flow-summary-row'); row.type = 'button';
        row.append(make('span', label), make('span', pending ? `${pending} answer${pending === 1 ? '' : 's'} remaining` : 'Ready', pending ? 'is-pending' : 'is-ready'));
        row.addEventListener('click', () => show(index));
        summaryRows.append(row);
      });
      progress.value = ready;
      const message = `${ready} of ${steps.length} sections ready`;
      if (progressLabel.textContent !== message) progressLabel.textContent = message;
    }
    function show(index, focus = true) {
      if (locked) return;
      current = Math.max(0, Math.min(index, steps.length - 1));
      const [key, label, help] = steps[current];
      cards.forEach(card => { card.hidden = card.dataset.reportStage !== key; });
      buttons.forEach(({button}, item) => {
        if (item === current) button.setAttribute('aria-current', 'step');
        else button.removeAttribute('aria-current');
      });
      if (warning) warning.hidden = current !== 0;
      summary.hidden = key !== 'finish';
      position.textContent = `STEP ${current + 1} OF ${steps.length}`;
      title.textContent = label; description.textContent = help;
      previous.disabled = current === 0;
      next.hidden = current === steps.length - 1;
      submit.hidden = current !== steps.length - 1;
      content.scrollTop = 0;
      update();
      if (focus) title.focus({preventScroll:true});
    }
    function reveal(input) {
      const card = input.closest('[data-report-stage]');
      const index = steps.findIndex(([key]) => key === card?.dataset.reportStage);
      if (index >= 0) show(index, false);
      const details = input.closest('details');
      if (details) details.open = true;
    }
    function advance() {
      const first = invalid(steps[current][0])[0];
      if (first) { reveal(first); first.reportValidity(); update(); return; }
      show(current + 1);
    }
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    form.addEventListener('report:draft-restored', update);
    form.addEventListener('report:before-validate', () => {
      const first = invalid()[0];
      if (first) reveal(first);
    });
    form.addEventListener('submit', event => {
      if (current === steps.length - 1) return;
      event.preventDefault(); event.stopImmediatePropagation(); advance();
    }, true);
    form.addEventListener('report:locked', () => {
      locked = true;
      next.disabled = true; previous.disabled = true;
      buttons.forEach(({button}) => { button.disabled = true; });
      update();
    });
    const firstPending = steps.findIndex(([key]) => invalid(key).length > 0);
    show(firstPending < 0 ? steps.length - 1 : firstPending, false);
  });
})();
