const modalOpeners = new WeakMap();

(() => {
  const rootSelector = "[data-interview-options-root]";
  const listSelector = "[data-interview-options-list]";
  const rowSelector = "[data-interview-option-row]";
  const addSelector = "[data-add-interview-option]";
  const removeSelector = "[data-remove-interview-option]";

  const optionsList = (root) => root?.querySelector(listSelector);
  const optionRows = (root) => {
    const list = optionsList(root);
    if (!list) return [];
    return Array.from(list.children).filter((child) => child.matches?.(rowSelector));
  };

  const syncOptionRows = (root) => {
    const rows = optionRows(root);
    const maxOptions = Number(root?.dataset?.maxOptions || 5);
    const addButton = root?.querySelector(addSelector);
    if (addButton) addButton.disabled = rows.length >= maxOptions;
    rows.forEach((row, index) => {
      const removeButton = row.querySelector(removeSelector);
      if (!removeButton) return;
      removeButton.hidden = index === 0;
      removeButton.disabled = false;
    });
    window.syncPotentialProceedInterviewButton?.(root?.closest("form"));
  };

  const addOption = (button) => {
    if (!button || button.disabled) return false;
    const root = button.closest(rootSelector);
    const list = optionsList(root);
    const rows = optionRows(root);
    const maxOptions = Number(root?.dataset?.maxOptions || 5);
    if (!root || !list || !rows.length || rows.length >= maxOptions) return false;
    const clone = rows[rows.length - 1].cloneNode(true);
    clone.classList.add("is-extra");
    clone.querySelectorAll("input, select, textarea").forEach((field) => {
      if (field.type === "checkbox" || field.type === "radio") field.checked = false;
      else field.value = "";
      field.disabled = false;
    });
    clone.querySelectorAll("button").forEach((rowButton) => {
      rowButton.disabled = false;
    });
    list.insertBefore(clone, button);
    syncOptionRows(root);
    clone.scrollIntoView?.({ block: "nearest" });
    clone.querySelector("input, select, textarea")?.focus();
    return true;
  };

  const removeOption = (button) => {
    if (!button || button.disabled) return false;
    const root = button.closest(rootSelector);
    const row = button.closest(rowSelector);
    const rows = optionRows(root);
    if (!root || !row) return false;
    if (rows.length <= 1) {
      row.querySelectorAll("input, select, textarea").forEach((field) => {
        if (field.type === "checkbox" || field.type === "radio") field.checked = false;
        else field.value = "";
      });
    } else {
      row.remove();
    }
    syncOptionRows(root);
    return true;
  };

  document.addEventListener("click", (event) => {
    const addButton = event.target.closest?.(addSelector);
    if (addButton) {
      if (addOption(addButton)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      return;
    }
    const removeButton = event.target.closest?.(removeSelector);
    if (removeButton && removeOption(removeButton)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  document.querySelectorAll(rootSelector).forEach(syncOptionRows);
})();

(() => {
  const referencePaymentNumber = "PAY-2026-0022";
  const syncFinancePaymentCardHeight = () => {
    const cards = Array.from(document.querySelectorAll(".finance-payment-request-grid .finance-request-card"));
    if (!cards.length) return;
    const referenceCard = cards.find((card) => card.dataset.paymentNumber === referencePaymentNumber);
    if (!referenceCard) return;

    const previousHeight = referenceCard.style.height;
    const previousMinHeight = referenceCard.style.minHeight;
    const previousMaxHeight = referenceCard.style.maxHeight;
    referenceCard.style.height = "auto";
    referenceCard.style.minHeight = "0";
    referenceCard.style.maxHeight = "none";
    const measuredHeight = Math.ceil(referenceCard.getBoundingClientRect().height);
    referenceCard.style.height = previousHeight;
    referenceCard.style.minHeight = previousMinHeight;
    referenceCard.style.maxHeight = previousMaxHeight;
    if (measuredHeight > 0) {
      document.documentElement.style.setProperty("--finance-payment-card-height", `${measuredHeight}px`);
    }
  };

  window.addEventListener("load", syncFinancePaymentCardHeight);
  window.addEventListener("resize", syncFinancePaymentCardHeight);
  syncFinancePaymentCardHeight();
})();

(() => {
  const dropdownSelector = ".finance-fixed-detail-dropdown";
  const summarySelector = ".finance-fixed-detail-link";
  const closeDropdowns = (except = null) => {
    document.querySelectorAll(dropdownSelector).forEach((dropdown) => {
      if (dropdown !== except) dropdown.removeAttribute("open");
    });
  };

  document.addEventListener("click", (event) => {
    const dropdown = event.target.closest?.(dropdownSelector);
    if (!dropdown) {
      closeDropdowns();
      return;
    }
    if (event.target.closest?.(summarySelector)) {
      closeDropdowns(dropdown);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDropdowns();
  });
})();

(() => {
  const statuses = ["Pending", "Waiting for confirmation", "Confirmed"];
  const classPrefix = "date-confirmation-";
  const classForStatus = (status) => `${classPrefix}${status.toLowerCase().replace(/\s+/g, "-")}`;
  const nextStatus = (status) => statuses[Math.min(statuses.indexOf(status) + 1, statuses.length - 1)] || statuses[0];
  const previousStatus = (status) => statuses[Math.max(statuses.indexOf(status) - 1, 0)] || statuses[0];

  const renderChip = (chip, status) => {
    const previous = chip.dataset.status || statuses[0];
    chip.classList.remove(classForStatus(previous));
    chip.classList.add(classForStatus(status));
    chip.dataset.status = status;
    chip.innerHTML = `<span data-date-confirmation-label>${status}</span>${status === "Pending" ? "" : '<span class="date-confirmation-back-arrow" aria-hidden="true">&lt;--</span>'}`;
  };

  document.addEventListener("click", async (event) => {
    const chip = event.target.closest("[data-date-confirmation-chip]");
    if (!chip || chip.disabled) return;

    const currentStatus = chip.dataset.status || statuses[0];
    const clickedBack = Boolean(event.target.closest(".date-confirmation-back-arrow"));
    const status = clickedBack ? previousStatus(currentStatus) : nextStatus(currentStatus);
    if (status === currentStatus) return;

    const formData = new FormData();
    formData.set("csrf_token", chip.dataset.csrfToken || document.querySelector("input[name='csrf_token']")?.value || "");
    formData.set("date_confirmation_status", status);
    renderChip(chip, status);
    chip.disabled = true;

    try {
      const response = await fetch(chip.dataset.action || "", { method: "POST", body: formData });
      if (!response.ok) throw new Error(await response.text());
      const payload = await response.json();
      renderChip(chip, payload.date_confirmation_status || status);
    } catch (error) {
      renderChip(chip, currentStatus);
      window.alert("The date confirmation status could not be updated. Please try again.");
    } finally {
      chip.disabled = false;
    }
  });
})();

(() => {
  const proceedButtonSelector = "[data-proceed-interview-button]";
  const cleanDigits = (value) => String(value || "").replace(/\D/g, "");
  const normalizeDate = (value) => {
    const raw = String(value || "").trim();
    if (!raw) return "";
    if (raw.includes("/")) {
      const parts = raw.split("/").map((part) => cleanDigits(part));
      if (parts.length === 3 && parts[2].length === 4) {
        return `${parts[0].padStart(2, "0").slice(-2)}/${parts[1].padStart(2, "0").slice(-2)}/${parts[2]}`;
      }
    }
    const digits = cleanDigits(raw);
    if (digits.length === 8) return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
    return raw;
  };
  const dateIsComplete = (value) => {
    const match = normalizeDate(value).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!match) return false;
    const day = Number.parseInt(match[1], 10);
    const monthIndex = Number.parseInt(match[2], 10) - 1;
    const year = Number.parseInt(match[3], 10);
    const parsed = new Date(year, monthIndex, day);
    return (
      !Number.isNaN(parsed.getTime()) &&
      parsed.getDate() === day &&
      parsed.getMonth() === monthIndex &&
      parsed.getFullYear() === year
    );
  };
  const normalizeTime = (value) => {
    const raw = String(value || "").replace(/h\.?/gi, "").trim();
    if (!raw) return "";
    const digits = cleanDigits(raw);
    if (raw.includes(":")) {
      const [hours = "", minutes = ""] = raw.split(":");
      const cleanHours = cleanDigits(hours);
      const cleanMinutes = cleanDigits(minutes);
      if (!cleanHours) return "";
      return `${cleanHours.padStart(2, "0").slice(-2)}:${(cleanMinutes || "00").padStart(2, "0").slice(0, 2)}`;
    }
    if (digits.length <= 2) return `${digits.padStart(2, "0")}:00`;
    if (digits.length === 3) return `${digits.slice(0, 1).padStart(2, "0")}:${digits.slice(1)}`;
    if (digits.length >= 4) return `${digits.slice(0, 2)}:${digits.slice(2, 4)}`;
    return "";
  };
  const timeIsComplete = (value) => {
    const match = normalizeTime(value).match(/^(\d{2}):(\d{2})$/);
    if (!match) return false;
    const hours = Number.parseInt(match[1], 10);
    const minutes = Number.parseInt(match[2], 10);
    return hours >= 0 && hours <= 24 && minutes >= 0 && minutes <= 60;
  };
  const syncButton = (form) => {
    const button = form?.querySelector?.(proceedButtonSelector);
    if (!button) return;
    const dateFields = Array.from(form.querySelectorAll('input[name="interview_option_date"]'));
    const timeFields = Array.from(form.querySelectorAll('input[name="interview_option_time"]'));
    const hasDateAndTime = dateFields.some((dateField, index) => (
      dateIsComplete(dateField?.value) && timeIsComplete(timeFields[index]?.value)
    ));
    const platform = form.querySelector('select[name="interview_option_platform"]')?.value.trim();
    const interviewer = form.querySelector('select[name="interview_option_interviewer"]')?.value.trim();
    const canProceed = Boolean(hasDateAndTime && platform && interviewer);
    button.disabled = !canProceed;
    if (canProceed) {
      button.removeAttribute("title");
    } else {
      button.setAttribute("title", "Complete at least one date and time, platform, and interviewer before proceeding.");
    }
  };
  const syncFromTarget = (target) => {
    const form = target?.closest?.("form") || target?.querySelector?.("form") || target;
    if (form?.querySelector?.(proceedButtonSelector)) syncButton(form);
  };
  const syncAll = () => {
    document.querySelectorAll(proceedButtonSelector).forEach((button) => syncButton(button.closest("form")));
  };
  window.syncPotentialProceedInterviewButton = syncFromTarget;
  window.syncPotentialProceedInterviewButtons = syncAll;
  ["input", "change", "keyup", "blur", "paste"].forEach((eventName) => {
    document.addEventListener(eventName, (event) => {
      syncFromTarget(event.target);
      window.requestAnimationFrame(syncAll);
    }, true);
  });
  syncAll();
})();

(() => {
  const syncInterviewInvitationActions = (form) => {
    const root = form?.querySelector?.("[data-interview-confirm-root]");
    if (!root) return;
    const noReply = root.querySelector("[data-interview-no-reply]");
    const choices = Array.from(root.querySelectorAll("[data-interview-option-choice]"));
    const noReplyChecked = Boolean(noReply?.checked);
    if (noReplyChecked) {
      choices.forEach((choice) => {
        choice.checked = false;
        choice.disabled = true;
      });
    } else {
      choices.forEach((choice) => {
        choice.disabled = false;
      });
    }
    const hasSelectedChoice = choices.some((choice) => choice.checked);
    const rejectButton = form.querySelector("[data-interview-turn-down-button]");
    const confirmButton = form.querySelector("[data-interview-confirm-button]");
    const reviewButton = form.querySelector("[data-review-date-time-options-button]");
    if (rejectButton) {
      rejectButton.disabled = !noReplyChecked;
      if (noReplyChecked) rejectButton.removeAttribute("title");
      else rejectButton.setAttribute("title", "Select No reply before rejecting the entry.");
    }
    if (confirmButton) {
      confirmButton.disabled = !hasSelectedChoice;
      if (hasSelectedChoice) confirmButton.removeAttribute("title");
      else confirmButton.setAttribute("title", "Select one date/time option before confirming the interview.");
    }
    if (reviewButton) {
      const canReview = !noReplyChecked && !hasSelectedChoice;
      reviewButton.disabled = !canReview;
      if (canReview) reviewButton.removeAttribute("title");
      else reviewButton.setAttribute("title", "Clear No reply and date/time selection to review options.");
    }
  };
  const syncFromControl = (control) => {
    const root = control?.closest?.("[data-interview-confirm-root]");
    const form = root?.closest?.("form");
    if (!root || !form) return;
    const noReply = root.querySelector("[data-interview-no-reply]");
    if (control.matches?.("[data-interview-no-reply]") && control.checked) {
      root.querySelectorAll("[data-interview-option-choice]").forEach((choice) => {
        choice.checked = false;
      });
    }
    if (control.matches?.("[data-interview-option-choice]") && control.checked) {
      if (noReply) noReply.checked = false;
      root.querySelectorAll("[data-interview-option-choice]").forEach((choice) => {
        if (choice !== control) choice.checked = false;
      });
    }
    syncInterviewInvitationActions(form);
  };
  const syncAll = () => {
    document.querySelectorAll("[data-interview-confirm-root]").forEach((root) => {
      syncInterviewInvitationActions(root.closest("form"));
    });
  };
  window.syncPotentialInterviewInvitationActions = syncInterviewInvitationActions;
  document.addEventListener("change", (event) => {
    const control = event.target.closest?.("[data-interview-no-reply], [data-interview-option-choice]");
    if (!control) return;
    syncFromControl(control);
    window.requestAnimationFrame(syncAll);
  }, true);
  document.addEventListener("click", (event) => {
    const control = event.target.closest?.("[data-interview-no-reply], [data-interview-option-choice]");
    if (!control) return;
    window.requestAnimationFrame(() => syncFromControl(control));
  }, true);
  syncAll();
})();

(() => {
  const parseDdMmYyyyDate = (value) => {
    const match = String(value || "").trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!match) return null;
    const day = Number.parseInt(match[1], 10);
    const monthIndex = Number.parseInt(match[2], 10) - 1;
    const year = Number.parseInt(match[3], 10);
    const parsed = new Date(year, monthIndex, day);
    if (
      Number.isNaN(parsed.getTime()) ||
      parsed.getDate() !== day ||
      parsed.getMonth() !== monthIndex ||
      parsed.getFullYear() !== year
    ) {
      return null;
    }
    return parsed;
  };
  const isFutureDdMmYyyyDate = (value) => {
    const parsed = parseDdMmYyyyDate(value);
    if (!parsed) return false;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return parsed >= today;
  };
  const syncOutcomePanels = (root) => {
    if (!root) return;
    const form = root.closest?.("form");
    const selected = root.querySelector("[data-induction-status-option]:checked")?.value || "";
    root.querySelectorAll("[data-induction-status-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.inductionStatusPanel !== selected;
    });

    const reactivationDateField = root.querySelector("[data-reactivation-date-field]");
    const acceptanceOutcome = root.querySelector("input[name='entry_acceptance_outcome']:checked")?.value || "";
    if (reactivationDateField) reactivationDateField.hidden = acceptanceOutcome !== "on_hold";

    const rejectButton = form?.querySelector("[data-induction-reject-button]");
    const rescheduleButton = form?.querySelector("[data-induction-reschedule-button]");
    const acceptedButton = form?.querySelector("[data-application-accepted-button]");
    const acceptedOnHoldButton = form?.querySelector("[data-application-accepted-on-hold-button]");
    const activateButton = form?.querySelector("[data-induction-activate-button]");
    const hasCar = Boolean(root.querySelector("input[name='interview_has_car']:checked"));
    const hasRole = Boolean(root.querySelector("input[name='interview_roles']:checked"));
    const acceptanceChecksContainer = form?.querySelector("[data-interview-acceptance-checks]");
    if (acceptanceChecksContainer) {
      acceptanceChecksContainer.hidden = acceptanceOutcome !== "sessions_pre_confirmation";
      if (acceptanceOutcome !== "sessions_pre_confirmation") {
        acceptanceChecksContainer.querySelectorAll("[data-interview-acceptance-required]").forEach((field) => {
          field.checked = false;
        });
      }
    }
    const acceptanceChecksComplete = acceptanceOutcome !== "sessions_pre_confirmation" || Array.from(form?.querySelectorAll("[data-interview-acceptance-required]") || []).every((field) => field.checked);
    const rescheduleFields = Array.from(root.querySelectorAll("[data-induction-reschedule-required]"));
    const rescheduleComplete = selected === "reschedule" && rescheduleFields.every((field) => {
      if (field.disabled) return false;
      if (field.type === "checkbox") return field.checked;
      return Boolean(field.value?.trim());
    });
    const noShowCheck = root.querySelector("[data-induction-no-show-required]");
    const noShowComplete = selected === "no_show" && (!noShowCheck || noShowCheck.checked);
    const attendedComplete = selected === "attended";
    const interviewAttendedComplete = selected === "attended" && hasCar && hasRole && acceptanceOutcome === "sessions_pre_confirmation" && acceptanceChecksComplete;
    const reactivationDate = root.querySelector("[data-reactivation-date]")?.value || "";
    const interviewOnHoldComplete = selected === "attended" && hasCar && hasRole && acceptanceOutcome === "on_hold" && isFutureDdMmYyyyDate(reactivationDate);
    const interviewPreassigned = form?.querySelector("[data-interview-preassigned-readonly]");
    if (interviewPreassigned) interviewPreassigned.hidden = selected !== "attended";

    if (rejectButton) rejectButton.disabled = !noShowComplete;
    if (rescheduleButton) rescheduleButton.disabled = !rescheduleComplete;
    if (activateButton) activateButton.disabled = !attendedComplete;
    if (acceptedButton) acceptedButton.disabled = !interviewAttendedComplete;
    if (acceptedOnHoldButton) acceptedOnHoldButton.disabled = !interviewOnHoldComplete;
  };

  const rootFromTarget = (target) => target?.closest?.("[data-induction-status-root]") || null;
  const syncFromTarget = (target) => {
    const root = rootFromTarget(target);
    if (root) syncOutcomePanels(root);
  };
  const syncAll = (scope = document) => {
    scope.querySelectorAll?.("[data-induction-status-root]").forEach(syncOutcomePanels);
  };
  window.syncPotentialOutcomeStatusPanels = syncOutcomePanels;
  window.syncPotentialOutcomeStatusPanelsIn = syncAll;
  ["change", "input", "click", "keyup", "blur"].forEach((eventName) => {
    document.addEventListener(eventName, (event) => {
      const control = event.target.closest?.("[data-induction-status-option], [data-induction-reschedule-required], [data-induction-no-show-required], [data-interview-acceptance-required], input[name='interview_has_car'], input[name='interview_roles'], input[name='entry_acceptance_outcome'], [data-reactivation-date]");
      if (!control) return;
      syncFromTarget(control);
      window.requestAnimationFrame(() => syncAll());
    }, true);
  });
  syncAll();
})();

(() => {
  const requiredNames = [
    "entry_accepted_notes_checked",
    "entry_accepted_email_sent",
    "entry_accepted_whatsapp_sent",
    "entry_accepted_pre_confirmation_sent",
  ];
  const syncButton = (form) => {
    const button = form?.querySelector?.("[data-onboarding-email-sent-button]");
    if (!button) return;
    const canMarkSent = requiredNames.every((name) => form.querySelector(`input[name="${name}"]`)?.checked);
    button.disabled = !canMarkSent;
    if (canMarkSent) {
      button.removeAttribute("title");
    } else {
      button.setAttribute("title", "Complete all four checks before marking onboarding email as sent.");
    }
  };
  const syncFromTarget = (target) => {
    const form = target?.closest?.("form") || target?.querySelector?.("form") || target;
    if (form?.querySelector?.("[data-onboarding-email-sent-button]")) syncButton(form);
  };
  const syncAll = (scope = document) => {
    scope.querySelectorAll?.("[data-onboarding-email-sent-button]").forEach((button) => syncButton(button.closest("form")));
  };
  window.syncPotentialEntryAcceptedOnboardingButton = syncFromTarget;
  window.syncPotentialEntryAcceptedOnboardingButtonsIn = syncAll;
  ["change", "click", "keyup"].forEach((eventName) => {
    document.addEventListener(eventName, (event) => {
      const checkbox = event.target.closest?.("[data-entry-accepted-check]");
      if (!checkbox) return;
      syncFromTarget(checkbox);
      window.requestAnimationFrame(() => syncAll());
    }, true);
  });
  syncAll();
})();

(() => {
  const syncControls = (form) => {
    const root = form?.querySelector?.("[data-onboarding-follow-up]");
    if (!form || !root) return;
    root.querySelectorAll("[data-interview-option-platform]").forEach((select) => {
      if (typeof window.syncInterviewOptionPlatformPreview === "function") {
        window.syncInterviewOptionPlatformPreview(select);
      }
    });
    const choice = root.querySelector("[data-onboarding-choice]:checked")?.value || "";
    root.querySelectorAll("[data-onboarding-panel]").forEach((panel) => {
      panel.classList.toggle("is-active", panel.dataset.onboardingPanel === choice);
    });
    root.querySelectorAll("[data-onboarding-fieldset]").forEach((fieldset) => {
      fieldset.disabled = fieldset.dataset.onboardingFieldset !== choice;
    });
	    const confirmComplete = choice === "confirm" && Array.from(root.querySelectorAll("[data-onboarding-confirm-required]")).every((field) => {
	      if (field.closest("[data-onboarding-fieldset]")?.disabled) return false;
	      if (field.type === "checkbox") return field.checked;
	      return Boolean(field.value?.trim());
	    });
    const turnDownComplete = choice === "turn_down" && Array.from(root.querySelectorAll("[data-onboarding-turn-down-required]")).every((field) => {
      if (field.closest("[data-onboarding-fieldset]")?.disabled) return false;
      return field.checked;
    });
    const confirmButton = form.querySelector("[data-onboarding-confirm-button]");
    const turnDownButton = form.querySelector("[data-onboarding-turn-down-button]");
    if (confirmButton) {
      confirmButton.disabled = !confirmComplete;
      if (confirmComplete) confirmButton.removeAttribute("title");
      else confirmButton.setAttribute("title", "Complete all required confirm application fields.");
    }
    if (turnDownButton) {
      turnDownButton.disabled = !turnDownComplete;
      if (turnDownComplete) turnDownButton.removeAttribute("title");
      else turnDownButton.setAttribute("title", "Complete both turn down application checks.");
    }
  };
  const syncFromTarget = (target) => {
    const form = target?.closest?.("form") || target?.querySelector?.("form") || target;
    if (form?.querySelector?.("[data-onboarding-follow-up]")) syncControls(form);
  };
  const syncAll = (scope = document) => {
    scope.querySelectorAll?.("[data-onboarding-follow-up]").forEach((root) => syncControls(root.closest("form")));
  };
  window.syncPotentialOnboardingFollowUpControls = syncFromTarget;
  window.syncPotentialOnboardingFollowUpControlsIn = syncAll;
  ["change", "input", "keyup", "blur"].forEach((eventName) => {
    document.addEventListener(eventName, (event) => {
      const control = event.target.closest?.("[data-onboarding-choice], [data-onboarding-confirm-required], [data-onboarding-turn-down-required]");
      if (!control) return;
      syncFromTarget(control);
      window.requestAnimationFrame(() => syncAll());
    }, true);
  });
  syncAll();
})();

const initStaffInductionTimeInputs = () => {
  const selector = "input[name='upcoming_induction_session_start_time'], input[name='upcoming_induction_session_end_time'], input[name='annual_meeting_time'][data-annual-meeting-time]";
  const inputFromTarget = (target) => target?.closest?.(selector) || null;
  const cleanDigits = (value) => String(value || "").replace(/\D/g, "");
  const formatTyping = (value) => {
    const raw = String(value || "").replace(/h\.?/gi, "").trim();
    if (raw.includes(":")) {
      const [hours = "", minutes = ""] = raw.split(":");
      return `${cleanDigits(hours).slice(0, 2)}:${cleanDigits(minutes).slice(0, 2)}`.slice(0, 5);
    }
    const digits = cleanDigits(raw).slice(0, 4);
    if (digits.length <= 2) return digits;
    return `${digits.slice(0, 2)}:${digits.slice(2)}`;
  };
  const normalize = (value) => {
    const raw = String(value || "").replace(/h\.?/gi, "").trim();
    if (!raw) return "";
    const digits = cleanDigits(raw);
    if (raw.includes(":")) {
      const [hours = "", minutes = ""] = raw.split(":");
      const cleanHours = cleanDigits(hours);
      const cleanMinutes = cleanDigits(minutes);
      if (!cleanHours) return "";
      return `${cleanHours.padStart(2, "0").slice(-2)}:${(cleanMinutes || "00").padStart(2, "0").slice(0, 2)}`;
    }
    if (digits.length <= 2) return `${digits.padStart(2, "0")}:00`;
    if (digits.length === 3) return `${digits.slice(0, 1).padStart(2, "0")}:${digits.slice(1)}`;
    return `${digits.slice(0, 2)}:${digits.slice(2, 4)}`;
  };
  const colonAdvance = (value) => {
    const raw = String(value || "").trim();
    if (!raw) return "";
    if (!raw.includes(":")) {
      const hours = cleanDigits(raw).slice(0, 2);
      return hours ? `${hours.padStart(2, "0")}:` : "";
    }
    return normalize(raw);
  };
  const parseMinutes = (value) => {
    const match = String(value || "").trim().match(/^(\d{2}):(\d{2})$/);
    if (!match) return null;
    const hours = Number.parseInt(match[1], 10);
    const minutes = Number.parseInt(match[2], 10);
    if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null;
    return (hours * 60) + minutes;
  };
  const validateRow = (row) => {
    if (!row) return;
    const startInput = row.querySelector("input[name='upcoming_induction_session_start_time']");
    const endInput = row.querySelector("input[name='upcoming_induction_session_end_time']");
    const startMinutes = parseMinutes(startInput?.value);
    const endMinutes = parseMinutes(endInput?.value);
    [startInput, endInput].forEach((input) => {
      if (!input?.setCustomValidity) return;
      const currentMinutes = parseMinutes(input.value);
      let message = "";
      if (input.value.trim() && currentMinutes === null) {
        message = "Please enter a valid 24-hour time.";
      } else if (startMinutes !== null && endMinutes !== null && startMinutes >= endMinutes) {
        message = input === startInput ? "Start time must be earlier than end time." : "End time must be later than start time.";
      }
      input.setCustomValidity(message);
    });
  };
  const validateSingleTimeInput = (input) => {
    if (!input?.setCustomValidity) return;
    input.setCustomValidity(input.value.trim() && parseMinutes(input.value) === null ? "Please enter a valid 24-hour time." : "");
  };
  const complete = (input) => {
    if (!input) return;
    input.value = normalize(input.value);
    const row = input.closest("[data-induction-option-row]");
    if (row) {
      validateRow(row);
    } else {
      validateSingleTimeInput(input);
    }
  };
  const focusNext = (input) => {
    const row = input?.closest?.("[data-induction-option-row]");
    if (!row) return;
    const fields = Array.from(row.querySelectorAll(selector)).filter((field) => !field.disabled);
    const nextField = fields[fields.indexOf(input) + 1];
    nextField?.focus();
  };
  document.addEventListener("input", (event) => {
    const input = inputFromTarget(event.target);
    if (!input) return;
    input.value = formatTyping(input.value);
    const row = input.closest("[data-induction-option-row]");
    if (row) {
      validateRow(row);
    } else {
      validateSingleTimeInput(input);
    }
  }, true);
  document.addEventListener("blur", (event) => {
    complete(inputFromTarget(event.target));
  }, true);
  document.addEventListener("change", (event) => {
    complete(inputFromTarget(event.target));
  }, true);
  document.addEventListener("keydown", (event) => {
    const input = inputFromTarget(event.target);
    if (!input) return;
    if (event.key === ":") {
      event.preventDefault();
      input.value = colonAdvance(input.value);
      const row = input.closest("[data-induction-option-row]");
      if (row) {
        validateRow(row);
      } else {
        validateSingleTimeInput(input);
      }
      return;
    }
    if (event.key === "Tab") complete(input);
    if (event.key === "Shift") input.dataset.staffInductionShiftAdvance = "true";
    if (event.shiftKey && event.key !== "Shift") delete input.dataset.staffInductionShiftAdvance;
  }, true);
  document.addEventListener("keyup", (event) => {
    if (event.key !== "Shift") return;
    const input = inputFromTarget(event.target);
    if (!input) return;
    const shouldAdvance = input.dataset.staffInductionShiftAdvance === "true";
    delete input.dataset.staffInductionShiftAdvance;
    complete(input);
    if (shouldAdvance) focusNext(input);
  }, true);
};

initStaffInductionTimeInputs();

const initStaffInductionDateInputs = () => {
  const selector = "input[name='upcoming_induction_session_date'][data-date-mask]";
  const inputFromTarget = (target) => target?.closest?.(selector) || null;
  const today = () => {
    const value = new Date();
    value.setHours(0, 0, 0, 0);
    return value;
  };
  const digitsOnly = (value) => String(value || "").replace(/\D/g, "");
  const formatTyping = (value) => {
    const raw = String(value || "");
    if (raw.includes("/")) {
      const parts = raw.split("/").slice(0, 3);
      const day = digitsOnly(parts[0]).slice(0, 2);
      const monthDigits = digitsOnly(parts[1]);
      const month = monthDigits.slice(0, 2);
      const year = `${monthDigits.slice(2)}${digitsOnly(parts[2])}`.slice(0, 4);
      if (parts.length === 2 && monthDigits.length > 2) return `${day}/${month}/${year}`.slice(0, 10);
      if (parts.length >= 3) return `${day}/${month}/${year}`.slice(0, 10);
      return `${day}/${month}${raw.endsWith("/") && month ? "/" : ""}`.slice(0, 10);
    }
    const clean = digitsOnly(raw).slice(0, 8);
    if (clean.length <= 2) return clean;
    if (clean.length <= 4) return `${clean.slice(0, 2)}/${clean.slice(2)}`;
    return `${clean.slice(0, 2)}/${clean.slice(2, 4)}/${clean.slice(4)}`;
  };
  const slashAdvance = (value) => {
    const raw = String(value || "").trim();
    if (!raw) return "";
    const parts = raw.split("/").slice(0, 3);
    const day = digitsOnly(parts[0]).slice(0, 2);
    if (!raw.includes("/")) return day ? `${day.padStart(2, "0")}/` : "";
    const month = digitsOnly(parts[1]).slice(0, 2);
    const year = digitsOnly(parts[2]).slice(0, 4);
    if (parts.length === 2) {
      if (!month) return day ? `${day.padStart(2, "0")}/` : "";
      return `${day.padStart(2, "0")}/${month.padStart(2, "0")}/${year}`.slice(0, 10);
    }
    return `${day.padStart(2, "0")}/${month.padStart(2, "0")}/${year}`.slice(0, 10);
  };
  const normalize = (value) => {
    const raw = String(value || "").trim();
    if (!raw) return "";
    const clean = digitsOnly(raw).slice(0, 8);
    if (raw.includes("/")) {
      const parts = raw.split("/").slice(0, 3);
      const day = digitsOnly(parts[0]).slice(0, 2);
      const month = digitsOnly(parts[1]).slice(0, 2);
      const year = `${digitsOnly(parts[1]).slice(2)}${digitsOnly(parts[2])}`.slice(0, 4);
      if (parts.length >= 3 && year.length) return `${day.padStart(2, "0")}/${month.padStart(2, "0")}/${year}`.slice(0, 10);
    }
    if (clean.length <= 2) return clean.padStart(2, "0");
    if (clean.length <= 4) return `${clean.slice(0, 2)}/${clean.slice(2).padStart(2, "0")}`;
    return `${clean.slice(0, 2)}/${clean.slice(2, 4)}/${clean.slice(4)}`;
  };
  const parseDate = (value) => {
    const match = String(value || "").trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!match) return null;
    const day = Number.parseInt(match[1], 10);
    const monthIndex = Number.parseInt(match[2], 10) - 1;
    const year = Number.parseInt(match[3], 10);
    if (day < 1 || day > 31 || monthIndex < 0 || monthIndex > 11 || year < today().getFullYear()) return null;
    const parsed = new Date(year, monthIndex, day);
    parsed.setHours(0, 0, 0, 0);
    if (parsed.getDate() !== day || parsed.getMonth() !== monthIndex || parsed.getFullYear() !== year) return null;
    return parsed;
  };
  const validate = (input) => {
    if (!input?.setCustomValidity) return;
    const raw = String(input.value || "").trim();
    const parsed = parseDate(raw);
    let message = "";
    if (raw && !parsed) message = "Please enter a valid date.";
    if (parsed && parsed < today()) message = "Date cannot be in the past.";
    input.setCustomValidity(message);
  };
  const setEndCursor = (input) => {
    if (typeof input?.setSelectionRange !== "function") return;
    const cursorPosition = input.value.length;
    input.setSelectionRange(cursorPosition, cursorPosition);
  };
  const complete = (input) => {
    if (!input) return;
    input.value = normalize(input.value);
    validate(input);
    setEndCursor(input);
  };
  document.addEventListener("input", (event) => {
    const input = inputFromTarget(event.target);
    if (!input) return;
    input.value = formatTyping(input.value);
    validate(input);
    setEndCursor(input);
  }, true);
  document.addEventListener("blur", (event) => complete(inputFromTarget(event.target)), true);
  document.addEventListener("change", (event) => complete(inputFromTarget(event.target)), true);
  document.addEventListener("keydown", (event) => {
    const input = inputFromTarget(event.target);
    if (!input) return;
    if (event.key === "/") {
      event.preventDefault();
      input.value = slashAdvance(input.value);
      validate(input);
      setEndCursor(input);
      return;
    }
    if (event.key === "Shift") input.dataset.staffInductionDateShiftAdvance = "true";
    if (event.shiftKey && event.key !== "Shift") delete input.dataset.staffInductionDateShiftAdvance;
  }, true);
  document.addEventListener("keyup", (event) => {
    if (event.key !== "Shift") return;
    const input = inputFromTarget(event.target);
    if (!input || input.dataset.staffInductionDateShiftAdvance !== "true") return;
    delete input.dataset.staffInductionDateShiftAdvance;
    input.value = slashAdvance(input.value);
    validate(input);
    setEndCursor(input);
  }, true);
};

initStaffInductionDateInputs();

const initRemoteTrainingPeriodInputs = () => {
  const selector = "input[name='remote_training_period'][data-remote-training-period]";
  const inputFromTarget = (target) => target?.closest?.(selector) || null;
  const today = () => {
    const value = new Date();
    value.setHours(0, 0, 0, 0);
    return value;
  };
  const digitsOnly = (value) => String(value || "").replace(/\D/g, "");
  const dateFromDigits = (digits) => {
    const clean = digitsOnly(digits).slice(0, 8);
    if (clean.length <= 2) return clean;
    if (clean.length <= 4) return `${clean.slice(0, 2)}/${clean.slice(2)}`;
    return `${clean.slice(0, 2)}/${clean.slice(2, 4)}/${clean.slice(4)}`;
  };
  const formatRangeTyping = (value) => {
    const clean = digitsOnly(value).slice(0, 16);
    const first = dateFromDigits(clean.slice(0, 8));
    const second = dateFromDigits(clean.slice(8, 16));
    if (clean.length >= 8) return `${first} to ${second}`.slice(0, 24);
    return first;
  };
  const splitRange = (value) => {
    const raw = String(value || "");
    if (raw.includes(" to ")) {
      const [first = "", second = ""] = raw.split(" to ");
      return [first, second];
    }
    const clean = digitsOnly(raw);
    return [dateFromDigits(clean.slice(0, 8)), dateFromDigits(clean.slice(8, 16))];
  };
  const padActiveSegment = (value) => {
    const raw = String(value || "");
    const [firstRaw, secondRaw] = splitRange(raw);
    const editingSecond = raw.includes(" to ");
    const parts = (editingSecond ? secondRaw : firstRaw).split("/");
    const day = digitsOnly(parts[0]).slice(0, 2);
    const month = digitsOnly(parts[1]).slice(0, 2);
    const year = digitsOnly(parts[2]).slice(0, 4);
    let formatted = "";
    if (parts.length <= 1) {
      formatted = day ? `${day.padStart(2, "0")}/` : "";
    } else if (parts.length === 2) {
      formatted = month ? `${day.padStart(2, "0")}/${month.padStart(2, "0")}/` : `${day.padStart(2, "0")}/`;
    } else {
      formatted = `${day.padStart(2, "0")}/${month.padStart(2, "0")}/${year}`;
    }
    if (editingSecond) return `${firstRaw} to ${formatted}`.slice(0, 24);
    return formatted;
  };
  const normalizeRange = (value) => {
    const clean = digitsOnly(value).slice(0, 16);
    const first = dateFromDigits(clean.slice(0, 8));
    const second = dateFromDigits(clean.slice(8, 16));
    if (clean.length > 8) return `${first} to ${second}`.slice(0, 24);
    if (clean.length === 8) return `${first} to `;
    return first;
  };
  const parseDate = (value) => {
    const match = String(value || "").trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!match) return null;
    const day = Number.parseInt(match[1], 10);
    const monthIndex = Number.parseInt(match[2], 10) - 1;
    const year = Number.parseInt(match[3], 10);
    if (day < 1 || day > 31 || monthIndex < 0 || monthIndex > 11 || year < today().getFullYear()) return null;
    const parsed = new Date(year, monthIndex, day);
    parsed.setHours(0, 0, 0, 0);
    if (parsed.getDate() !== day || parsed.getMonth() !== monthIndex || parsed.getFullYear() !== year) return null;
    return parsed;
  };
  const validationMessage = (input) => {
    const raw = String(input?.value || "").trim();
    if (!raw) return "";
    const selectedYear = Number.parseInt(input.dataset.certificationYear || "", 10);
    const [startValue, endValue] = raw.split(" to ");
    if (!startValue || !endValue || raw.split(" to ").length !== 2) return "Remote training period must use DD/MM/YYYY to DD/MM/YYYY.";
    const start = parseDate(startValue);
    const end = parseDate(endValue);
    if (!start || !end) return "Please enter valid dates.";
    if (selectedYear && (start.getFullYear() !== selectedYear || end.getFullYear() !== selectedYear)) {
      return `Remote training period dates must be in ${selectedYear}.`;
    }
    if (start < today() || end < today()) return "Date cannot be in the past.";
    if (start >= end) return "Remote training period start date must be earlier than the end date.";
    return "";
  };
  const validate = (input) => {
    if (!input?.setCustomValidity) return;
    input.setCustomValidity(validationMessage(input));
  };
  const setEndCursor = (input) => {
    if (typeof input?.setSelectionRange !== "function") return;
    const cursorPosition = input.value.length;
    input.setSelectionRange(cursorPosition, cursorPosition);
  };
  const complete = (input) => {
    if (!input) return;
    input.value = normalizeRange(input.value);
    validate(input);
    setEndCursor(input);
  };
  document.addEventListener("input", (event) => {
    const input = inputFromTarget(event.target);
    if (!input) return;
    input.value = formatRangeTyping(input.value);
    validate(input);
    setEndCursor(input);
  }, true);
  document.addEventListener("blur", (event) => complete(inputFromTarget(event.target)), true);
  document.addEventListener("change", (event) => complete(inputFromTarget(event.target)), true);
  document.addEventListener("keydown", (event) => {
    const input = inputFromTarget(event.target);
    if (!input) return;
    if (event.key === "/") {
      event.preventDefault();
      input.value = padActiveSegment(input.value);
      validate(input);
      setEndCursor(input);
      return;
    }
    if (event.key === "Shift") input.dataset.remoteTrainingShiftAdvance = "true";
    if (event.shiftKey && event.key !== "Shift") delete input.dataset.remoteTrainingShiftAdvance;
  }, true);
  document.addEventListener("keyup", (event) => {
    if (event.key !== "Shift") return;
    const input = inputFromTarget(event.target);
    if (!input || input.dataset.remoteTrainingShiftAdvance !== "true") return;
    delete input.dataset.remoteTrainingShiftAdvance;
    input.value = padActiveSegment(input.value);
    validate(input);
    setEndCursor(input);
  }, true);
};

initRemoteTrainingPeriodInputs();

const dismissFlashNotification = (button) => {
  const flash = button?.closest?.("[data-dismissible-flash], .flash");
  if (!flash) return;
  const stack = flash.closest(".flash-stack");
  flash.remove();
  if (stack && !stack.children.length) {
    stack.hidden = true;
  }
};

const createFlashCloseButton = () => {
  const button = document.createElement("button");
  button.className = "flash-close-button";
  button.type = "button";
  button.setAttribute("aria-label", "Dismiss notification");
  button.dataset.dismissFlash = "true";
  button.innerHTML = "&times;";
  return button;
};

const appendFlashContent = (item, message) => {
  item.dataset.dismissibleFlash = "true";
  const text = document.createElement("span");
  text.className = "flash-message";
  text.textContent = message;
  item.replaceChildren(text, createFlashCloseButton());
};

const flashNotificationMessage = (flash) => (
  flash?.querySelector?.(".flash-message")?.textContent || flash?.textContent || ""
).trim();

document.addEventListener("click", (event) => {
  const button = event.target.closest?.("[data-dismiss-flash]");
  if (!button) return;
  event.preventDefault();
  dismissFlashNotification(button);
});

document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  const inputId = button.dataset.passwordInput;
  const input = inputId ? document.getElementById(inputId) : null;
  if (!input) return;

  button.addEventListener("click", () => {
    const shouldShowPassword = input.type === "password";
    input.type = shouldShowPassword ? "text" : "password";
    button.setAttribute("aria-label", shouldShowPassword ? "Hide password" : "Show password");
  });
});

document.querySelectorAll("[data-status-track-toggle]").forEach((button) => {
  const panel = document.getElementById(button.getAttribute("aria-controls") || "");
  if (!panel) return;

  button.addEventListener("click", () => {
    const shouldOpen = panel.hidden;
    panel.hidden = !shouldOpen;
    button.setAttribute("aria-expanded", String(shouldOpen));
  });
});

const getFocusableElements = (container) => Array.from(container.querySelectorAll(
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), details summary, [tabindex]:not([tabindex="-1"])'
)).filter((element) => {
  if (element.closest("[hidden]")) return false;
  const style = window.getComputedStyle(element);
  return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
});

const focusModalHeading = (modal) => {
  const labelledBy = modal.getAttribute("aria-labelledby");
  const heading = labelledBy ? document.getElementById(labelledBy) : null;
  const focusTarget = heading || getFocusableElements(modal)[0];
  focusTarget?.focus({ preventScroll: true });
};

const openModal = (id, { opener = null, focus = true } = {}) => {
  const modal = document.getElementById(id);
  if (!modal) return;
  if (opener) modalOpeners.set(modal, opener);
  modal.classList.add("is-open");
  modal.setAttribute("aria-hidden", "false");
  window.syncPotentialOutcomeStatusPanelsIn?.(modal);
  modal.querySelectorAll("[data-interview-confirm-root]").forEach((root) => {
    window.syncPotentialInterviewInvitationActions?.(root.closest("form"));
  });
  window.syncPotentialEntryAcceptedOnboardingButtonsIn?.(modal);
  window.syncPotentialOnboardingFollowUpControlsIn?.(modal);
  if (focus) {
    window.requestAnimationFrame(() => focusModalHeading(modal));
  }
};

const setPotentialInfoEditing = (section, isEditing) => {
  if (!section) return;
  const view = section.querySelector("[data-potential-info-view]");
  const form = section.querySelector("[data-potential-info-edit]");
  const editButton = section.querySelector("[data-edit-potential-info]");
  if (!view || !form) return;
  view.hidden = isEditing;
  form.hidden = !isEditing;
  if (editButton) editButton.hidden = isEditing;
  section.querySelectorAll("[data-potential-note-delete]").forEach((deleteForm) => {
    deleteForm.hidden = !isEditing;
  });
  if (isEditing) {
    window.requestAnimationFrame(() => {
      form.querySelector("input:not([type='hidden']), select, textarea")?.focus();
    });
  }
};

document.addEventListener("click", (event) => {
  const editButton = event.target.closest("[data-edit-potential-info]");
  if (editButton) {
    event.preventDefault();
    event.stopPropagation();
    setPotentialInfoEditing(editButton.closest(".potential-review-summary"), true);
    return;
  }

  const cancelButton = event.target.closest("[data-cancel-potential-info-edit]");
  if (cancelButton) {
    event.preventDefault();
    event.stopPropagation();
    const form = cancelButton.closest("form");
    form?.reset();
    setPotentialInfoEditing(cancelButton.closest(".potential-review-summary"), false);
  }
});

const targetAliases = {
  schedule: "schedule-actions",
  "schedule-status": "schedule-actions",
  "schedule-gate": "schedule-actions",
  core_readiness: "readiness",
  "core-readiness": "readiness",
  operational_readiness: "readiness",
  "operational-readiness": "readiness",
  session_readiness: "readiness",
  "session-readiness": "readiness",
  "incident-review": "incidents",
  shipment: "shipments",
  journey: "journey",
};

const targetLabels = {
  overview: "Session overview",
  "schedule-actions": "Schedule",
  "schedule-overview": "Schedule",
  "schedule-notes": "Notes",
  staffing: "Staffing",
  logistics: "Logistics",
  packages: "Packages",
  "package-label-verification": "Candidate label verification",
  "package-label-printing": "Candidate label printing and affixing",
  "package-room-package-sealing": "Room package sealing",
  "package-return-packages": "Return packages",
  "package-staff-member-ids": "Staff member IDs",
  "package-inclusion-final-items": "Inclusion of final items",
  "package-session-box-sealing": "Session box sealing",
  shipments: "Shipments",
  finance: "Finance",
  sinapsis: "Sinapsis",
  communications: "Communications",
  readiness: "Readiness",
  "session-readiness": "Session readiness",
  incidents: "Incidents",
  "priority-action": "Priority action",
  journey: "Journey",
  history: "History",
  activity: "Activity",
};

const relatedFocusedTargets = {
  "schedule-actions": ["schedule-actions", "schedule-overview", "history"],
  "schedule-notes": ["schedule-notes", "schedule-actions", "schedule-overview", "history"],
  "schedule-overview": ["schedule-overview", "schedule-actions"],
  "package-label-verification": ["packages", "package-label-verification"],
  "package-label-printing": ["packages", "package-label-printing"],
  "package-room-package-sealing": ["packages", "package-room-package-sealing"],
  "package-return-packages": ["packages", "package-return-packages"],
  "package-staff-member-ids": ["packages", "package-staff-member-ids"],
  "package-inclusion-final-items": ["packages", "package-inclusion-final-items"],
  "package-session-box-sealing": ["packages", "package-session-box-sealing"],
  readiness: ["readiness", "session-readiness"],
  "session-readiness": ["readiness", "session-readiness"],
  incidents: ["incidents"],
  logistics: ["logistics"],
  finance: ["finance"],
  sinapsis: ["sinapsis"],
  communications: ["communications"],
  shipments: ["shipments"],
  journey: ["journey"],
  history: ["history", "schedule-actions"],
  activity: ["activity"],
};

const modalTargetKey = (targetId) => {
  if (!targetId) return "";
  const lastDash = targetId.lastIndexOf("-");
  return lastDash === -1 ? targetId : targetId.slice(0, lastDash);
};

const resolveModalTarget = (targetId) => {
  if (!targetId) return null;
  let target = document.getElementById(targetId);
  if (target) return target;
  const lastDash = targetId.lastIndexOf("-");
  if (lastDash === -1) return null;
  const targetKey = targetId.slice(0, lastDash);
  const sessionId = targetId.slice(lastDash + 1);
  const alias = targetAliases[targetKey];
  if (alias) {
    target = document.getElementById(`${alias}-${sessionId}`);
    if (target) return target;
  }
  return document.querySelector(`[data-section-aliases~="${CSS.escape(targetKey)}"][id$="-${CSS.escape(sessionId)}"]`);
};

const expandControlSection = (section) => {
  if (!section) return;
  section.classList.remove("is-collapsed");
  const toggle = section.querySelector(":scope > .staffing-control-header [data-control-section-toggle]");
  if (toggle) {
    toggle.setAttribute("aria-expanded", "true");
    toggle.textContent = "Collapse";
  }
};

const setControlSectionCollapsed = (section, isCollapsed) => {
  if (!section) return;
  section.classList.toggle("is-collapsed", isCollapsed);
  const toggle = section.querySelector(":scope > .staffing-control-header [data-control-section-toggle]");
  if (toggle) {
    const title = section.querySelector(":scope > .staffing-control-header h3")?.textContent?.trim() || "section";
    toggle.setAttribute("aria-expanded", String(!isCollapsed));
    toggle.setAttribute("aria-label", `${isCollapsed ? "Expand" : "Collapse"} ${title}`);
    toggle.textContent = isCollapsed ? "Expand" : "Collapse";
  }
};

const collapseUnrelatedControlSections = (modal, targetId) => {
  const key = modalTargetKey(targetId);
  const relatedKeys = new Set([key, ...(relatedFocusedTargets[key] || [])]);
  modal.querySelectorAll("[data-control-section]").forEach((section) => {
    const sectionKey = modalTargetKey(section.id);
    if (relatedKeys.has(sectionKey)) {
      setControlSectionCollapsed(section, false);
      return;
    }
    const hasVisibleError = section.querySelector(".schedule-form-error:not([hidden]), .flash.error");
    if (hasVisibleError) return;
    setControlSectionCollapsed(section, true);
  });
};

const resetControlSectionsToDefault = (modal) => {
  modal.querySelectorAll("[data-control-section]").forEach((section) => {
    setControlSectionCollapsed(section, section.dataset.defaultCollapsed === "true");
  });
};

const syncScheduleNoteContextInputs = (modal) => {
  if (!modal) return;
  const focusedContext = [
    ["is-logistics-only", "logistics"],
    ["is-finance-only", "finance"],
    ["is-sinapsis-only", "sinapsis"],
    ["is-communications-only", "communications"],
  ].find(([className]) => modal.classList.contains(className))?.[1] || "";
  modal.querySelectorAll("[data-schedule-note-focused-context]").forEach((input) => {
    input.value = focusedContext;
  });
  modal.querySelectorAll("[data-schedule-note-textarea]").forEach((textarea) => {
    textarea.placeholder = focusedContext === "logistics"
      ? textarea.dataset.logisticsPlaceholder || "Add a logistics note"
      : textarea.dataset.schedulePlaceholder || "Add a schedule note";
  });
};

const clearFocusedMode = (modal) => {
  if (!modal) return;
  modal.classList.remove("is-focused-mode");
  modal.classList.remove("is-schedule-only");
  modal.classList.remove("is-staffing-only");
  modal.classList.remove("is-packages-only");
  modal.classList.remove("is-shipments-only");
  modal.classList.remove("is-logistics-only");
  modal.classList.remove("is-finance-only");
  modal.classList.remove("is-sinapsis-only");
  modal.classList.remove("is-communications-only");
  syncScheduleNoteContextInputs(modal);
  delete modal.dataset.focusedTarget;
  const context = modal.querySelector("[data-focused-context]");
  if (context) {
    context.hidden = true;
    context.textContent = "";
  }
  const returnButton = modal.querySelector("[data-view-full-session-overview]");
  if (returnButton) returnButton.hidden = true;
};

const setFocusedMode = (modal, targetId, label = "") => {
  if (!modal || !targetId) return;
  const key = modalTargetKey(targetId);
  if (!key || key === "overview") {
    clearFocusedMode(modal);
    return;
  }
  const title = label || targetLabels[key] || "Focused view";
  const sessionTitle = modal.querySelector(".modal-header h2")?.textContent?.trim() || "";
  modal.classList.add("is-focused-mode");
  modal.dataset.focusedTarget = key;
  const context = modal.querySelector("[data-focused-context]");
  if (context) {
    context.textContent = `Focused view: ${title}${sessionTitle ? ` - ${sessionTitle}` : ""}`;
    context.hidden = false;
  }
  const returnButton = modal.querySelector("[data-view-full-session-overview]");
  if (returnButton) returnButton.hidden = false;
  collapseUnrelatedControlSections(modal, targetId);
};

const highlightModalTarget = (target) => {
  target.classList.remove("is-target-highlighted");
  window.requestAnimationFrame(() => {
    target.classList.add("is-target-highlighted");
    window.setTimeout(() => target.classList.remove("is-target-highlighted"), 1800);
  });
};

const focusModalTarget = (targetId, { scroll = true } = {}) => {
  const target = resolveModalTarget(targetId);
  if (!target) return false;
  const section = target.closest("[data-control-section]");
  expandControlSection(section);
  const targetKey = modalTargetKey(targetId);
  if (scroll) {
    const scrollBehavior = targetKey.startsWith("package-") ? "auto" : "smooth";
    target.scrollIntoView({ block: "start", behavior: scrollBehavior });
  }
  target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: true });
  highlightModalTarget(target);
  return true;
};

const closeModal = (modal) => {
  modal.querySelectorAll("form").forEach((form) => {
    form.reset();
  });
  modal.classList.remove("is-open");
  modal.setAttribute("aria-hidden", "true");
  clearFocusedMode(modal);
  resetControlSectionsToDefault(modal);
  modal.querySelectorAll("[data-interview-confirm-root]").forEach((root) => syncInterviewInvitationConfirmation(root.closest("form")));
  modal.querySelectorAll("[data-induction-status-root]").forEach(syncInductionStatusPanels);
  modal.querySelectorAll("[data-onboarding-follow-up]").forEach((root) => syncOnboardingFollowUpControls(root.closest("form")));
  modal.querySelectorAll("[data-interview-no-show]").forEach((checkbox) => syncPotentialInterviewNoShow(checkbox.closest("form")));
  const opener = modalOpeners.get(modal);
  if (opener && document.contains(opener)) opener.focus();
  const closeRedirectUrl = modal.dataset.closeRedirectUrl;
  if (closeRedirectUrl) {
    delete modal.dataset.closeRedirectUrl;
    window.location.assign(closeRedirectUrl);
  }
};

const openRequestedSessionModal = () => {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("open_session_modal");
  if (!sessionId) return;
  if (params.get("session_fullscreen") === "1") return;
  openModal(`exam-session-members-${sessionId}`);
  params.delete("open_session_modal");
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", nextUrl);
};

const openRequestedScheduleModal = () => {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("open_schedule_modal");
  if (!sessionId) return;
  openModal(`schedule-workflow-${sessionId}`, { focus: false });
  const modalTarget = params.get("open_modal_target");
  const actionKey = params.get("open_schedule_action");
  const scheduleOnly = params.get("schedule_only") === "1";
  const staffingOnly = params.get("staffing_only") === "1";
  const packagesOnly = params.get("packages_only") === "1";
  const shipmentsOnly = params.get("shipments_only") === "1";
  const logisticsOnly = params.get("logistics_only") === "1";
  const financeOnly = params.get("finance_only") === "1";
  const sinapsisOnly = params.get("sinapsis_only") === "1";
  const communicationsOnly = params.get("communications_only") === "1";
  const modal = document.getElementById(`schedule-workflow-${sessionId}`);
  if (modal) {
    delete modal.dataset.closeRedirectUrl;
    if (params.get("close_view") === "bundles") {
      const closeParams = new URLSearchParams(params);
      closeParams.set("view", "bundles");
      closeParams.delete("bundle_id");
      closeParams.delete("open_schedule_modal");
      closeParams.delete("open_modal_target");
      closeParams.delete("open_schedule_action");
      closeParams.delete("schedule_only");
      closeParams.delete("staffing_only");
      closeParams.delete("packages_only");
      closeParams.delete("shipments_only");
      closeParams.delete("logistics_only");
      closeParams.delete("finance_only");
      closeParams.delete("sinapsis_only");
      closeParams.delete("communications_only");
      closeParams.delete("open_staffing_control");
      closeParams.delete("open_logistics_control");
      closeParams.delete("open_finance_control");
      closeParams.delete("open_sinapsis_control");
      closeParams.delete("open_communications_control");
      closeParams.delete("highlight_note");
      closeParams.delete("close_view");
      const closeQuery = closeParams.toString();
      modal.dataset.closeRedirectUrl = `${window.location.pathname}${closeQuery ? `?${closeQuery}` : ""}`;
    }
    modal.classList.toggle("is-schedule-only", scheduleOnly);
    modal.classList.toggle("is-staffing-only", staffingOnly);
    modal.classList.toggle("is-packages-only", packagesOnly);
    modal.classList.toggle("is-shipments-only", shipmentsOnly);
    modal.classList.toggle("is-logistics-only", logisticsOnly);
    modal.classList.toggle("is-finance-only", financeOnly);
    modal.classList.toggle("is-sinapsis-only", sinapsisOnly);
    modal.classList.toggle("is-communications-only", communicationsOnly);
    syncScheduleNoteContextInputs(modal);
  }
  if (actionKey) {
    const form = document.querySelector(`#schedule-workflow-${sessionId} [data-schedule-action-panel][data-schedule-action-key="${CSS.escape(actionKey)}"]`);
    const trigger = document.querySelector(`#schedule-workflow-${sessionId} [data-schedule-action-toggle][aria-controls="${form?.id || ""}"]`);
    if (form) {
      openScheduleActionPanel(form, trigger, { focus: false });
      const flash = document.querySelector(".flash.error");
      const errorBox = form.querySelector("[data-schedule-action-error]");
      if (flash && errorBox) {
        errorBox.textContent = flashNotificationMessage(flash);
        errorBox.hidden = false;
      }
    }
  }
  if (params.get("open_staffing_control") === "1") {
    const form = document.querySelector(`#schedule-workflow-${sessionId} [data-staffing-control-form]`);
    const trigger = document.querySelector(`#schedule-workflow-${sessionId} [data-staffing-control-toggle]`);
    if (form) {
      openStaffingControlForm(form, trigger, { focus: false });
      const flash = document.querySelector(".flash.error");
      const errorBox = form.querySelector("[data-staffing-control-error]");
      if (flash && errorBox) {
        errorBox.textContent = flashNotificationMessage(flash);
        errorBox.hidden = false;
      }
    }
  }
  if (params.get("open_logistics_control") === "1") {
    const form = document.querySelector(`#schedule-workflow-${sessionId} [data-logistics-control-form]`);
    const trigger = document.querySelector(`#schedule-workflow-${sessionId} [data-logistics-control-toggle]`);
    if (form) {
      openLogisticsControlForm(form, trigger, { focus: false });
      const flash = document.querySelector(".flash.error");
      const errorBox = form.querySelector("[data-logistics-control-error]");
      if (flash && errorBox) {
        errorBox.textContent = flashNotificationMessage(flash);
        errorBox.hidden = false;
      }
    }
  }
  if (params.get("open_finance_control") === "1") {
    const form = document.querySelector(`#schedule-workflow-${sessionId} [data-finance-control-form]`);
    const trigger = document.querySelector(`#schedule-workflow-${sessionId} [data-finance-control-toggle]`);
    if (form) {
      openFinanceControlForm(form, trigger, { focus: false });
      const flash = document.querySelector(".flash.error");
      const errorBox = form.querySelector("[data-finance-control-error]");
      if (flash && errorBox) {
        errorBox.textContent = flashNotificationMessage(flash);
        errorBox.hidden = false;
      }
    }
  }
  if (params.get("open_communications_control") === "1") {
    const form = document.querySelector(`#schedule-workflow-${sessionId} [data-communications-control-form]`);
    const trigger = document.querySelector(`#schedule-workflow-${sessionId} [data-communications-control-toggle]`);
    if (form) {
      openCommunicationsControlForm(form, trigger, { focus: false });
      const flash = document.querySelector(".flash.error");
      const errorBox = form.querySelector("[data-communications-control-error]");
      if (flash && errorBox) {
        errorBox.textContent = flashNotificationMessage(flash);
        errorBox.hidden = false;
      }
    }
  }
  params.delete("open_schedule_modal");
  params.delete("open_modal_target");
  params.delete("open_schedule_action");
  params.delete("schedule_only");
  params.delete("staffing_only");
  params.delete("packages_only");
  params.delete("shipments_only");
  params.delete("logistics_only");
  params.delete("finance_only");
  params.delete("sinapsis_only");
  params.delete("communications_only");
  params.delete("open_staffing_control");
  params.delete("open_logistics_control");
  params.delete("open_finance_control");
  params.delete("open_sinapsis_control");
  params.delete("open_communications_control");
  params.delete("highlight_note");
  params.delete("close_view");
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", nextUrl);
  if (modalTarget) {
    window.requestAnimationFrame(() => {
      const targetId = `${modalTarget}-${sessionId}`;
      setFocusedMode(modal, targetId);
      if (modal) {
        modal.classList.toggle("is-schedule-only", scheduleOnly);
        modal.classList.toggle("is-staffing-only", staffingOnly);
        modal.classList.toggle("is-packages-only", packagesOnly);
        modal.classList.toggle("is-shipments-only", shipmentsOnly);
        modal.classList.toggle("is-logistics-only", logisticsOnly);
        modal.classList.toggle("is-finance-only", financeOnly);
        modal.classList.toggle("is-sinapsis-only", sinapsisOnly);
        modal.classList.toggle("is-communications-only", communicationsOnly);
        syncScheduleNoteContextInputs(modal);
      }
      if (!focusModalTarget(targetId, { scroll: !modalTarget.startsWith("package-") })) {
        focusModalHeading(modal);
      }
    });
  } else {
    window.requestAnimationFrame(() => focusModalHeading(document.getElementById(`schedule-workflow-${sessionId}`)));
  }
};

const openRequestedStaffModal = () => {
  const params = new URLSearchParams(window.location.search);
  const modalId = params.get("open_staff_modal");
  if (!modalId) return;
  openModal(modalId);
  const highlightNoteId = params.get("highlight_note");
  if (highlightNoteId) {
    window.requestAnimationFrame(() => {
      const target = document.getElementById(`potential-note-${highlightNoteId}`);
      if (!target) return;
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      target.setAttribute("tabindex", "-1");
      target.focus({ preventScroll: true });
      highlightModalTarget(target);
    });
  }
  params.delete("open_staff_modal");
  params.delete("highlight_note");
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", nextUrl);
};

document.querySelectorAll("[data-note-read-checkbox]").forEach((checkbox) => {
  checkbox.addEventListener("change", () => {
    if (!checkbox.checked) return;
    const form = checkbox.closest("[data-note-read-form]");
    form?.requestSubmit();
  });
});

const closeScheduleActionPanel = (form, { restoreFocus = true } = {}) => {
  if (!form) return;
  form.hidden = true;
  const modal = form.closest(".modal");
  const trigger = modal?.querySelector(`[data-schedule-action-toggle][aria-controls="${CSS.escape(form.id)}"]`);
  trigger?.setAttribute("aria-expanded", "false");
  const errorBox = form.querySelector("[data-schedule-action-error]");
  if (errorBox) {
    errorBox.hidden = true;
    errorBox.textContent = "";
  }
  if (restoreFocus) trigger?.focus();
};

const syncScheduleLinkRequirement = (form) => {
  if (!form) return;
  const input = form.querySelector("[data-schedule-link-input]");
  const submit = form.querySelector("[data-schedule-link-submit]");
  if (!input || !submit) return;
  if (form.dataset.scheduleMonthlyBlocked === "true") {
    submit.disabled = true;
    return;
  }
  submit.disabled = !input.value.trim();
};

const openScheduleActionPanel = (form, trigger, { focus = true } = {}) => {
  if (!form) return;
  const modal = form.closest(".modal");
  modal?.querySelectorAll("[data-schedule-action-panel]").forEach((panel) => {
    if (panel !== form) closeScheduleActionPanel(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-staffing-control-form]").forEach((panel) => {
    closeStaffingControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-logistics-control-form]").forEach((panel) => {
    closeLogisticsControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-finance-control-form]").forEach((panel) => {
    closeFinanceControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-communications-control-form]").forEach((panel) => {
    closeCommunicationsControlForm(panel, { restoreFocus: false });
  });
  form.hidden = false;
  syncScheduleLinkRequirement(form);
  trigger?.setAttribute("aria-expanded", "true");
  if (focus) {
    window.requestAnimationFrame(() => {
      form.querySelector("input:not([type='hidden']), textarea, select, button")?.focus();
    });
  }
};

const closeStaffingControlForm = (form, { restoreFocus = true } = {}) => {
  if (!form) return;
  form.hidden = true;
  const modal = form.closest(".modal");
  const trigger = modal?.querySelector(`[data-staffing-control-toggle][aria-controls="${CSS.escape(form.id)}"]`);
  trigger?.setAttribute("aria-expanded", "false");
  const errorBox = form.querySelector("[data-staffing-control-error]");
  if (errorBox) {
    errorBox.hidden = true;
    errorBox.textContent = "";
  }
  if (restoreFocus) trigger?.focus();
};

const openStaffingControlForm = (form, trigger, { focus = true } = {}) => {
  if (!form) return;
  const modal = form.closest(".modal");
  document.querySelectorAll("[data-staffing-control-form]").forEach((panel) => {
    if (panel !== form) closeStaffingControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-logistics-control-form]").forEach((panel) => {
    closeLogisticsControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-finance-control-form]").forEach((panel) => {
    closeFinanceControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-communications-control-form]").forEach((panel) => {
    closeCommunicationsControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-schedule-action-panel]").forEach((panel) => {
    closeScheduleActionPanel(panel, { restoreFocus: false });
  });
  form.hidden = false;
  trigger?.setAttribute("aria-expanded", "true");
  if (focus) {
    window.requestAnimationFrame(() => {
      form.querySelector("input:not([type='hidden']):not([readonly]), textarea, select, button")?.focus();
    });
  }
};

const closeLogisticsControlForm = (form, { restoreFocus = true } = {}) => {
  if (!form) return;
  form.hidden = true;
  const modal = form.closest(".modal");
  const trigger = modal?.querySelector(`[data-logistics-control-toggle][aria-controls="${CSS.escape(form.id)}"]`);
  trigger?.setAttribute("aria-expanded", "false");
  const errorBox = form.querySelector("[data-logistics-control-error]");
  if (errorBox) {
    errorBox.hidden = true;
    errorBox.textContent = "";
  }
  if (restoreFocus) trigger?.focus();
};

const openLogisticsControlForm = (form, trigger, { focus = true } = {}) => {
  if (!form) return;
  const modal = form.closest(".modal");
  document.querySelectorAll("[data-logistics-control-form]").forEach((panel) => {
    if (panel !== form) closeLogisticsControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-staffing-control-form]").forEach((panel) => {
    closeStaffingControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-finance-control-form]").forEach((panel) => {
    closeFinanceControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-communications-control-form]").forEach((panel) => {
    closeCommunicationsControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-schedule-action-panel]").forEach((panel) => {
    closeScheduleActionPanel(panel, { restoreFocus: false });
  });
  form.hidden = false;
  trigger?.setAttribute("aria-expanded", "true");
  if (focus) {
    window.requestAnimationFrame(() => {
      form.querySelector("input:not([type='hidden']):not([readonly]), textarea, select, button")?.focus();
    });
  }
};

const syncFinanceNoteRequirement = (form) => {
  const statusSelect = form?.querySelector("[data-finance-status-select]");
  const note = form?.querySelector("[data-finance-note]");
  const hint = form?.querySelector("[data-finance-note-hint]");
  if (!statusSelect || !note || !hint) return;
  const requiredStatuses = (statusSelect.dataset.noteRequiredStatuses || "").split("|").filter(Boolean);
  const isRequired = requiredStatuses.includes(statusSelect.value);
  note.toggleAttribute("required", isRequired);
  hint.hidden = !isRequired;
};

const closeFinanceControlForm = (form, { restoreFocus = true } = {}) => {
  if (!form) return;
  form.hidden = true;
  const modal = form.closest(".modal");
  const trigger = modal?.querySelector(`[data-finance-control-toggle][aria-controls="${CSS.escape(form.id)}"]`);
  trigger?.setAttribute("aria-expanded", "false");
  const errorBox = form.querySelector("[data-finance-control-error]");
  if (errorBox) {
    errorBox.hidden = true;
    errorBox.textContent = "";
  }
  if (restoreFocus) trigger?.focus();
};

const openFinanceControlForm = (form, trigger, { focus = true } = {}) => {
  if (!form) return;
  const modal = form.closest(".modal");
  document.querySelectorAll("[data-finance-control-form]").forEach((panel) => {
    if (panel !== form) closeFinanceControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-staffing-control-form]").forEach((panel) => {
    closeStaffingControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-logistics-control-form]").forEach((panel) => {
    closeLogisticsControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-communications-control-form]").forEach((panel) => {
    closeCommunicationsControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-schedule-action-panel]").forEach((panel) => {
    closeScheduleActionPanel(panel, { restoreFocus: false });
  });
  syncFinanceNoteRequirement(form);
  form.hidden = false;
  trigger?.setAttribute("aria-expanded", "true");
  if (focus) {
    window.requestAnimationFrame(() => {
      form.querySelector("input:not([type='hidden']):not([readonly]), textarea, select, button")?.focus();
    });
  }
};

const syncCommunicationsNoteRequirement = (form) => {
  const statusSelect = form?.querySelector("[data-communications-status-select]");
  const note = form?.querySelector("[data-communications-note]");
  const hint = form?.querySelector("[data-communications-note-hint]");
  if (!statusSelect || !note || !hint) return;
  const isRequired = statusSelect.value === "Needs follow-up";
  note.toggleAttribute("required", isRequired);
  hint.hidden = !isRequired;
};

const closeCommunicationsControlForm = (form, { restoreFocus = true } = {}) => {
  if (!form) return;
  form.hidden = true;
  const modal = form.closest(".modal");
  const trigger = modal?.querySelector(`[data-communications-control-toggle][aria-controls="${CSS.escape(form.id)}"]`);
  trigger?.setAttribute("aria-expanded", "false");
  const errorBox = form.querySelector("[data-communications-control-error]");
  if (errorBox) {
    errorBox.hidden = true;
    errorBox.textContent = "";
  }
  if (restoreFocus) trigger?.focus();
};

const openCommunicationsControlForm = (form, trigger, { focus = true } = {}) => {
  if (!form) return;
  const modal = form.closest(".modal");
  document.querySelectorAll("[data-communications-control-form]").forEach((panel) => {
    if (panel !== form) closeCommunicationsControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-staffing-control-form]").forEach((panel) => {
    closeStaffingControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-logistics-control-form]").forEach((panel) => {
    closeLogisticsControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-finance-control-form]").forEach((panel) => {
    closeFinanceControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-schedule-action-panel]").forEach((panel) => {
    closeScheduleActionPanel(panel, { restoreFocus: false });
  });
  syncCommunicationsNoteRequirement(form);
  form.hidden = false;
  trigger?.setAttribute("aria-expanded", "true");
  if (focus) {
    window.requestAnimationFrame(() => {
      form.querySelector("input:not([type='hidden']):not([readonly]), textarea, select, button")?.focus();
    });
  }
};

const initializeControlSections = () => {
  document.querySelectorAll("[data-control-section]").forEach((section) => {
    const header = section.querySelector(":scope > .staffing-control-header");
    if (!header || header.querySelector("[data-control-section-toggle]") || !section.id) return;
    const title = header.querySelector("h3")?.textContent?.trim() || "section";
    const button = document.createElement("button");
    button.className = "secondary-button compact-action control-section-toggle";
    button.type = "button";
    button.dataset.controlSectionToggle = "";
    button.setAttribute("aria-controls", section.id);
    button.setAttribute("aria-expanded", "true");
    button.setAttribute("aria-label", `Collapse ${title}`);
    button.textContent = "Collapse";
    header.appendChild(button);
    if (section.dataset.defaultCollapsed === "true") {
      section.classList.add("is-collapsed");
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-label", `Expand ${title}`);
      button.textContent = "Expand";
    }
  });
};

initializeControlSections();

document.addEventListener("click", (event) => {
  const sectionToggle = event.target.closest("[data-control-section-toggle]");
  if (sectionToggle) {
    event.preventDefault();
    const section = document.getElementById(sectionToggle.getAttribute("aria-controls"));
    if (!section) return;
    const isCollapsed = section.classList.toggle("is-collapsed");
    const title = section.querySelector(":scope > .staffing-control-header h3")?.textContent?.trim() || "section";
    sectionToggle.setAttribute("aria-expanded", String(!isCollapsed));
    sectionToggle.setAttribute("aria-label", `${isCollapsed ? "Expand" : "Collapse"} ${title}`);
    sectionToggle.textContent = isCollapsed ? "Expand" : "Collapse";
    return;
  }

  const packagePreparationTrigger = event.target.closest("[data-start-package-preparation]");
  if (packagePreparationTrigger) {
    event.preventDefault();
    const panel = document.getElementById(packagePreparationTrigger.dataset.startPackagePreparation);
    if (!panel) return;
    panel.hidden = false;
    const addPanel = panel.matches("details") ? panel : panel.querySelector("details");
    if (addPanel) addPanel.open = true;
    packagePreparationTrigger.setAttribute("aria-expanded", "true");
    window.requestAnimationFrame(() => {
      panel.querySelector("summary, input:not([type='hidden']), select, textarea, button")?.focus();
    });
    return;
  }

  const packageRowAddButton = event.target.closest("[data-add-package-unit-row]");
  if (packageRowAddButton) {
    event.preventDefault();
    const form = packageRowAddButton.closest("[data-package-unit-create-form]");
    const rows = form?.querySelector("[data-package-unit-rows]");
    const template = form?.querySelector("template[data-package-unit-row-template]");
    const countInput = form?.querySelector("[data-package-row-count]");
    if (!form || !rows || !template || !countInput) return;
    const currentCount = rows.querySelectorAll("[data-package-unit-row]").length;
    if (currentCount >= 20) {
      packageRowAddButton.disabled = true;
      return;
    }
    const index = currentCount;
    const fragment = template.content.cloneNode(true);
    const row = fragment.querySelector("[data-package-unit-row]");
    if (!row) return;
    row.dataset.packageRowIndex = String(index);
    row.querySelectorAll("[name]").forEach((field) => {
      field.name = field.name.replace("__INDEX__", String(index));
    });
    rows.appendChild(fragment);
    countInput.value = String(index + 1);
    if (index + 1 >= 20) packageRowAddButton.disabled = true;
    window.requestAnimationFrame(() => {
      row.querySelector("input, select, textarea")?.focus();
    });
    return;
  }

  const modalNavLink = event.target.closest(".modal-section-nav a, .overview-quick-links a");
  if (modalNavLink) {
    const hash = modalNavLink.getAttribute("href");
    if (hash?.startsWith("#")) {
      const target = document.getElementById(hash.slice(1));
      if (target) {
        event.preventDefault();
        focusModalTarget(target.id);
      }
    }
    return;
  }

  const activityFilter = event.target.closest("[data-activity-source-filter]");
  if (activityFilter) {
    event.preventDefault();
    const section = activityFilter.closest(".session-activity-timeline");
    if (!section) return;
    const filter = activityFilter.dataset.activitySourceFilter;
    section.querySelectorAll("[data-activity-source-filter]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button === activityFilter));
    });
    section.querySelectorAll("[data-activity-source]").forEach((entry) => {
      entry.hidden = filter !== "all" && entry.dataset.activitySource !== filter;
    });
    return;
  }

  const opener = event.target.closest("[data-open-modal]");
  if (opener) {
    event.preventDefault();
    event.stopPropagation();
    const modal = document.getElementById(opener.dataset.openModal);
    const isOverviewMode = opener.dataset.modalMode === "overview";
    const isScheduleOnlyMode = opener.dataset.modalScheduleOnly === "true";
    const isStaffingOnlyMode = opener.dataset.modalStaffingOnly === "true";
    const isPackagesOnlyMode = opener.dataset.modalPackagesOnly === "true";
    const isShipmentsOnlyMode = opener.dataset.modalShipmentsOnly === "true";
    const isLogisticsOnlyMode = opener.dataset.modalLogisticsOnly === "true";
    const isFinanceOnlyMode = opener.dataset.modalFinanceOnly === "true";
    const isSinapsisOnlyMode = opener.dataset.modalSinapsisOnly === "true";
    const isCommunicationsOnlyMode = opener.dataset.modalCommunicationsOnly === "true";
    clearFocusedMode(modal);
    if (modal) modal.classList.toggle("is-schedule-only", isScheduleOnlyMode);
    if (modal) modal.classList.toggle("is-staffing-only", isStaffingOnlyMode);
    if (modal) modal.classList.toggle("is-packages-only", isPackagesOnlyMode);
    if (modal) modal.classList.toggle("is-shipments-only", isShipmentsOnlyMode);
    if (modal) modal.classList.toggle("is-logistics-only", isLogisticsOnlyMode);
    if (modal) modal.classList.toggle("is-finance-only", isFinanceOnlyMode);
    if (modal) modal.classList.toggle("is-sinapsis-only", isSinapsisOnlyMode);
    if (modal) modal.classList.toggle("is-communications-only", isCommunicationsOnlyMode);
    if (modal) {
      const returnInput = modal.querySelector("[data-payment-request-return-input]");
      if (returnInput && opener.dataset.paymentRequestReturnSessionId) {
        const returnUrl = new URL(window.location.href);
        returnUrl.searchParams.set("open_schedule_modal", opener.dataset.paymentRequestReturnSessionId);
        returnUrl.searchParams.set("open_modal_target", "logistics");
        returnUrl.searchParams.set("logistics_only", "1");
        returnUrl.hash = `logistics-${opener.dataset.paymentRequestReturnSessionId}`;
        returnInput.value = `${returnUrl.pathname}${returnUrl.search}${returnUrl.hash}`;
      }
      const logisticsConceptInput = modal.querySelector("[data-payment-request-logistics-concept-input]");
      if (logisticsConceptInput) {
        logisticsConceptInput.value = opener.dataset.paymentRequestLogisticsConceptId || "";
      }
    }
    syncScheduleNoteContextInputs(modal);
    resetControlSectionsToDefault(modal);
    openModal(opener.dataset.openModal, { opener, focus: !opener.dataset.modalScrollTarget });
    window.requestAnimationFrame(() => {
      if (opener.dataset.modalScrollTarget) {
        if (!isOverviewMode) setFocusedMode(modal, opener.dataset.modalScrollTarget, opener.dataset.modalTargetLabel);
        if (!focusModalTarget(opener.dataset.modalScrollTarget)) {
          focusModalHeading(modal);
        }
      }
    });
    return;
  }

  const overviewReturn = event.target.closest("[data-view-full-session-overview]");
  if (overviewReturn) {
    event.preventDefault();
    const modal = overviewReturn.closest(".modal");
    clearFocusedMode(modal);
    resetControlSectionsToDefault(modal);
    const overviewTarget = overviewReturn.dataset.overviewTarget;
    if (overviewTarget && !focusModalTarget(overviewTarget)) {
      focusModalHeading(modal);
    }
    return;
  }

  const scheduleActionToggle = event.target.closest("[data-schedule-action-toggle]");
  if (scheduleActionToggle) {
    event.preventDefault();
    const form = document.getElementById(scheduleActionToggle.getAttribute("aria-controls"));
    if (!form) return;
    if (!form.hidden) {
      closeScheduleActionPanel(form);
    } else {
      openScheduleActionPanel(form, scheduleActionToggle);
    }
    return;
  }

  const scheduleActionCancel = event.target.closest("[data-schedule-action-cancel]");
  if (scheduleActionCancel) {
    event.preventDefault();
    closeScheduleActionPanel(scheduleActionCancel.closest("[data-schedule-action-panel]"));
    return;
  }

  const staffingControlToggle = event.target.closest("[data-staffing-control-toggle]");
  if (staffingControlToggle) {
    event.preventDefault();
    const form = document.getElementById(staffingControlToggle.getAttribute("aria-controls"));
    if (!form) return;
    if (!form.hidden) {
      closeStaffingControlForm(form);
    } else {
      openStaffingControlForm(form, staffingControlToggle);
    }
    return;
  }

  const staffingControlCancel = event.target.closest("[data-staffing-control-cancel]");
  if (staffingControlCancel) {
    event.preventDefault();
    closeStaffingControlForm(staffingControlCancel.closest("[data-staffing-control-form]"));
    return;
  }

  const logisticsControlToggle = event.target.closest("[data-logistics-control-toggle]");
  if (logisticsControlToggle) {
    event.preventDefault();
    const form = document.getElementById(logisticsControlToggle.getAttribute("aria-controls"));
    if (!form) return;
    if (!form.hidden) {
      closeLogisticsControlForm(form);
    } else {
      openLogisticsControlForm(form, logisticsControlToggle);
    }
    return;
  }

  const logisticsControlCancel = event.target.closest("[data-logistics-control-cancel]");
  if (logisticsControlCancel) {
    event.preventDefault();
    closeLogisticsControlForm(logisticsControlCancel.closest("[data-logistics-control-form]"));
    return;
  }

  const financeControlToggle = event.target.closest("[data-finance-control-toggle]");
  if (financeControlToggle) {
    event.preventDefault();
    const form = document.getElementById(financeControlToggle.getAttribute("aria-controls"));
    if (!form) return;
    if (!form.hidden) {
      closeFinanceControlForm(form);
    } else {
      openFinanceControlForm(form, financeControlToggle);
    }
    return;
  }

  const financeControlCancel = event.target.closest("[data-finance-control-cancel]");
  if (financeControlCancel) {
    event.preventDefault();
    closeFinanceControlForm(financeControlCancel.closest("[data-finance-control-form]"));
    return;
  }

  const communicationsControlToggle = event.target.closest("[data-communications-control-toggle]");
  if (communicationsControlToggle) {
    event.preventDefault();
    const form = document.getElementById(communicationsControlToggle.getAttribute("aria-controls"));
    if (!form) return;
    if (!form.hidden) {
      closeCommunicationsControlForm(form);
    } else {
      openCommunicationsControlForm(form, communicationsControlToggle);
    }
    return;
  }

  const communicationsControlCancel = event.target.closest("[data-communications-control-cancel]");
  if (communicationsControlCancel) {
    event.preventDefault();
    closeCommunicationsControlForm(communicationsControlCancel.closest("[data-communications-control-form]"));
    return;
  }

  if (event.target.matches("[data-close-modal]")) {
    closeModal(event.target.closest(".modal"));
  }

  if (event.target.classList.contains("modal")) {
    closeModal(event.target);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Tab") {
    const openModals = document.querySelectorAll(".modal.is-open");
    const openModalElement = openModals[openModals.length - 1];
    if (!openModalElement) return;
    const focusable = getFocusableElements(openModalElement);
    if (!focusable.length) {
      event.preventDefault();
      focusModalHeading(openModalElement);
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
    return;
  }

  if (event.key === "Escape") {
    const openModals = document.querySelectorAll(".modal.is-open");
    const topModal = openModals[openModals.length - 1];
    if (!topModal) return;
    const openSchedulePanel = topModal.querySelector("[data-schedule-action-panel]:not([hidden])");
    if (openSchedulePanel) {
      event.preventDefault();
      closeScheduleActionPanel(openSchedulePanel);
      return;
    }
    const openStaffingControl = topModal.querySelector("[data-staffing-control-form]:not([hidden])");
    if (openStaffingControl) {
      event.preventDefault();
      closeStaffingControlForm(openStaffingControl);
      return;
    }
    const openLogisticsControl = topModal.querySelector("[data-logistics-control-form]:not([hidden])");
    if (openLogisticsControl) {
      event.preventDefault();
      closeLogisticsControlForm(openLogisticsControl);
      return;
    }
    const openFinanceControl = topModal.querySelector("[data-finance-control-form]:not([hidden])");
    if (openFinanceControl) {
      event.preventDefault();
      closeFinanceControlForm(openFinanceControl);
      return;
    }
    const openCommunicationsControl = topModal.querySelector("[data-communications-control-form]:not([hidden])");
    if (openCommunicationsControl) {
      event.preventDefault();
      closeCommunicationsControlForm(openCommunicationsControl);
      return;
    }
    event.preventDefault();
    closeModal(topModal);
  }
});

document.querySelectorAll("[data-finance-control-form]").forEach((form) => {
  syncFinanceNoteRequirement(form);
  form.querySelector("[data-finance-status-select]")?.addEventListener("change", () => {
    syncFinanceNoteRequirement(form);
  });
});

document.querySelectorAll("[data-communications-control-form]").forEach((form) => {
  syncCommunicationsNoteRequirement(form);
  form.querySelector("[data-communications-status-select]")?.addEventListener("change", () => {
    syncCommunicationsNoteRequirement(form);
  });
});

const syncStaffingRoleCheckRow = (checkbox) => {
  const row = checkbox?.closest("tr");
  if (!row) return;
  const verified = checkbox.checked && !checkbox.disabled;
  row.querySelectorAll("[data-role-check-dependent]").forEach((control) => {
    const isCopyButton = control.matches("[data-copy-text]");
    const targetHref = control.dataset.roleCheckHref || "";
    const hasTarget = isCopyButton
      ? Boolean((control.dataset.copyText || "").trim())
      : control.matches("a")
        ? Boolean(targetHref.trim() && targetHref.trim() !== "mailto:")
        : true;
    const enabled = verified && hasTarget;
    if (control.matches("a")) {
      control.href = enabled ? targetHref : "#";
      control.setAttribute("aria-disabled", enabled ? "false" : "true");
      if (enabled) {
        control.removeAttribute("tabindex");
      } else {
        control.setAttribute("tabindex", "-1");
      }
    } else {
      control.disabled = !enabled;
    }
    control.classList.toggle("is-disabled", !enabled);
    if (control.classList.contains("staffing-action-chip")) {
      control.classList.toggle("staffing-action-chip-blue", enabled);
      control.classList.toggle("staffing-action-chip-grey", !enabled);
    }
  });
};

document.querySelectorAll("[data-role-check-form]").forEach((form) => {
  const checkbox = form.querySelector("[data-role-check]");
  if (!checkbox) return;
  syncStaffingRoleCheckRow(checkbox);
  checkbox.addEventListener("change", async () => {
    const previousChecked = !checkbox.checked;
    syncStaffingRoleCheckRow(checkbox);
    if (!window.fetch) {
      form.submit();
      return;
    }
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || "Role check could not be updated.");
      }
      checkbox.checked = Boolean(payload.role_check_verified);
    } catch (error) {
      checkbox.checked = previousChecked;
      window.alert(error.message || "Role check could not be updated.");
    } finally {
      syncStaffingRoleCheckRow(checkbox);
    }
  });
});

document.querySelectorAll("[data-pre-logistics-provider-remove-form]").forEach((form) => {
  const checkbox = form.querySelector("[data-pre-logistics-provider-checkbox]");
  if (!checkbox) return;
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) return;
    if (!window.confirm("Are you sure you want to remove this provider option?")) {
      checkbox.checked = true;
      return;
    }
    form.submit();
  });
});

document.querySelectorAll("[data-pre-logistics-staff-remove-form]").forEach((form) => {
  const checkbox = form.querySelector("[data-pre-logistics-staff-checkbox]");
  if (!checkbox) return;
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) return;
    if (!window.confirm("Are you sure you want to remove this staff member from this concept?")) {
      checkbox.checked = true;
      return;
    }
    form.submit();
  });
});

document.querySelectorAll("[data-pre-logistics-status-select]").forEach((select) => {
  select.addEventListener("change", () => {
    select.closest("form")?.submit();
  });
});

openRequestedSessionModal();
openRequestedScheduleModal();
openRequestedStaffModal();

const scrollStateKey = `path-scroll-state:${window.location.pathname}${window.location.search}`;
const tableSortScrollStateKey = `path-table-sort-scroll-state:${window.location.pathname}`;

const saveTableSortScrollState = () => {
  const staffTable = document.querySelector("[data-staff-records-table]");
  sessionStorage.setItem(
    tableSortScrollStateKey,
    JSON.stringify({
      windowX: window.scrollX,
      windowY: window.scrollY,
      tableX: staffTable?.scrollLeft || 0,
      tableY: staffTable?.scrollTop || 0,
    })
  );
};

const restoreTableSortScrollState = () => {
  const savedState = sessionStorage.getItem(tableSortScrollStateKey);
  if (!savedState) return;
  sessionStorage.removeItem(tableSortScrollStateKey);
  try {
    const state = JSON.parse(savedState);
    const staffTable = document.querySelector("[data-staff-records-table]");
    if (staffTable) {
      staffTable.scrollLeft = Number(state.tableX) || 0;
      staffTable.scrollTop = Number(state.tableY) || 0;
    }
    window.scrollTo(Number(state.windowX) || 0, Number(state.windowY) || 0);
  } catch {
    sessionStorage.removeItem(tableSortScrollStateKey);
  }
};

document.querySelectorAll(".table-sort").forEach((sortLink) => {
  sortLink.addEventListener("click", saveTableSortScrollState);
});

const saveAnnualTableScrollState = () => {
  const tableWrap = document.querySelector("[data-annual-records-table]");
  if (!tableWrap) return;
  sessionStorage.setItem(
    scrollStateKey,
    JSON.stringify({
      windowX: window.scrollX,
      windowY: window.scrollY,
      tableX: tableWrap.scrollLeft,
      tableY: tableWrap.scrollTop,
    })
  );
};

const restoreAnnualTableScrollState = () => {
  const savedState = sessionStorage.getItem(scrollStateKey);
  if (!savedState) return;
  sessionStorage.removeItem(scrollStateKey);

  try {
    const state = JSON.parse(savedState);
    const tableWrap = document.querySelector("[data-annual-records-table]");
    if (tableWrap) {
      tableWrap.scrollLeft = Number(state.tableX) || 0;
      tableWrap.scrollTop = Number(state.tableY) || 0;
    }
    window.scrollTo(Number(state.windowX) || 0, Number(state.windowY) || 0);
  } catch {
    sessionStorage.removeItem(scrollStateKey);
  }
};

restoreAnnualTableScrollState();
restoreTableSortScrollState();

const normalizeFeeInputValue = (value) => {
  let output = "";
  let hasComma = false;
  for (const char of value) {
    if (/\d/.test(char)) {
      output += char;
    } else if (char === "," && !hasComma) {
      output += char;
      hasComma = true;
    }
  }
  const [integerPart, decimalPart] = output.split(",");
  if (decimalPart !== undefined) {
    return `${integerPart},${decimalPart.slice(0, 6)}`;
  }
  return output;
};

const isValidFeeValue = (value) => {
  if (!/^\d+(,\d{1,6})?$/.test(value)) return false;
  const amount = Number.parseFloat(value.replace(",", "."));
  return Number.isFinite(amount) && amount >= 0;
};

const syncFeeFormValidity = (form) => {
  const submit = form.querySelector("[data-fee-submit]");
  if (!submit) return;
  const description = form.querySelector("input[name='fee_description']")?.value.trim() || "";
  const currency = form.querySelector("select[name='currency']")?.value || "";
  const feeValue = form.querySelector("[data-fee-value]")?.value.trim() || "";
  const unit = form.querySelector("select[name='unit_of_measure']")?.value || "";
  submit.disabled = !(description && currency && isValidFeeValue(feeValue) && unit);
};

document.querySelectorAll("[data-fee-form]").forEach((form) => {
  form.querySelectorAll("input, select").forEach((field) => {
    field.addEventListener("input", () => syncFeeFormValidity(form));
    field.addEventListener("change", () => syncFeeFormValidity(form));
  });
  form.querySelectorAll("[data-fee-value]").forEach((input) => {
    input.addEventListener("input", () => {
      const normalized = normalizeFeeInputValue(input.value);
      if (input.value !== normalized) input.value = normalized;
      syncFeeFormValidity(form);
    });
  });
  syncFeeFormValidity(form);
});

document.querySelectorAll("[data-fee-month-picker]").forEach((picker) => {
  const syncSelectedMonths = () => {
    const list = picker.closest(".fee-month-field")?.querySelector("[data-fee-month-selected-list]");
    if (!list) return;
    list.textContent = "";
    picker.querySelectorAll("input[type='checkbox']:checked").forEach((checkbox) => {
      const chip = document.createElement("span");
      chip.className = "fee-month-selected-chip";
      chip.textContent = checkbox.value;
      list.appendChild(chip);
    });
  };
  picker.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.addEventListener("change", syncSelectedMonths);
  });
  picker.addEventListener("toggle", () => {
    if (!picker.open) return;
    document.querySelectorAll("[data-fee-month-picker][open]").forEach((otherPicker) => {
      if (otherPicker !== picker) otherPicker.open = false;
    });
  });
  syncSelectedMonths();
});

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-fee-month-picker]")) return;
  document.querySelectorAll("[data-fee-month-picker][open]").forEach((picker) => {
    picker.open = false;
  });
});

const futPickers = Array.from(document.querySelectorAll("[data-fut-picker]"));

const closeFutPicker = (picker) => {
  const trigger = picker.querySelector("[data-fut-picker-toggle]");
  const panel = picker.querySelector("[data-fut-picker-panel]");
  if (!trigger || !panel) return;
  panel.hidden = true;
  trigger.setAttribute("aria-expanded", "false");
};

const closeOtherFutPickers = (activePicker) => {
  futPickers.forEach((picker) => {
    if (picker !== activePicker) closeFutPicker(picker);
  });
};

const positionFutPicker = (picker) => {
  const trigger = picker.querySelector("[data-fut-picker-toggle]");
  const panel = picker.querySelector("[data-fut-picker-panel]");
  if (!trigger || !panel || panel.hidden) return;

  const margin = 12;
  const triggerRect = trigger.getBoundingClientRect();
  const panelRect = panel.getBoundingClientRect();
  const availableBelow = window.innerHeight - triggerRect.bottom - margin;
  const availableAbove = triggerRect.top - margin;
  const top = availableBelow >= panelRect.height || availableBelow >= availableAbove
    ? Math.min(triggerRect.bottom + 8, window.innerHeight - panelRect.height - margin)
    : Math.max(margin, triggerRect.top - panelRect.height - 8);
  const left = Math.max(
    margin,
    Math.min(triggerRect.left + (triggerRect.width / 2) - (panelRect.width / 2), window.innerWidth - panelRect.width - margin)
  );

  panel.style.top = `${Math.max(margin, top)}px`;
  panel.style.left = `${left}px`;
};

futPickers.forEach((picker) => {
  const trigger = picker.querySelector("[data-fut-picker-toggle]");
  const panel = picker.querySelector("[data-fut-picker-panel]");
  if (!trigger || !panel) return;

  trigger.addEventListener("click", () => {
    const shouldOpen = panel.hidden;
    closeOtherFutPickers(picker);
    panel.hidden = !shouldOpen;
    trigger.setAttribute("aria-expanded", String(shouldOpen));
    if (shouldOpen) {
      window.requestAnimationFrame(() => {
        positionFutPicker(picker);
        const firstOption = panel.querySelector("input:not(:disabled)");
        if (firstOption) firstOption.focus({ preventScroll: true });
      });
    }
  });

  picker.querySelectorAll("[data-fut-picker-close]").forEach((button) => {
    button.addEventListener("click", () => closeFutPicker(picker));
  });
});

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-fut-picker]")) return;
  futPickers.forEach(closeFutPicker);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    futPickers.forEach(closeFutPicker);
  }
});

["resize", "scroll"].forEach((eventName) => {
  window.addEventListener(eventName, () => {
    futPickers.forEach(positionFutPicker);
  }, { passive: true });
});

document.querySelectorAll(".table-wrap").forEach((tableWrap) => {
  tableWrap.addEventListener("scroll", () => {
    futPickers.forEach(positionFutPicker);
  }, { passive: true });
});

document.addEventListener("click", (event) => {
  const saveButton = event.target.closest("[data-acceptance-draft-save]");
  if (!saveButton) return;
  const form = saveButton.closest("form");
  const saveAction = saveButton.dataset.acceptanceDraftSave;
  if (!form || !saveAction) return;
  form.action = saveAction;
  form.submit();
});

document.addEventListener("input", (event) => {
  const scheduleLinkInput = event.target.closest("[data-schedule-link-input]");
  if (scheduleLinkInput) {
    syncScheduleLinkRequirement(scheduleLinkInput.closest("[data-schedule-action-panel]"));
  }
});

document.addEventListener("click", (event) => {
  const reopenDispatchButton = event.target.closest("[data-reopen-dispatch-stage]");
  if (!reopenDispatchButton) return;
  const panel = reopenDispatchButton.closest(".shipment-dispatch-status-panel");
  if (!panel) return;
  const message = reopenDispatchButton.dataset.confirmMessage || "Management password authorisation is required to reopen dispatch stages.";
  const expectedPassword = reopenDispatchButton.dataset.confirmPasswordValue || "EditOK";
  if (!window.confirm(message)) return;
  const password = window.prompt("Enter the confirmation password to continue:");
  if (password !== expectedPassword) {
    window.alert("Incorrect password. The action was cancelled.");
    return;
  }
  panel.querySelectorAll(".shipment-dispatch-checkbox-form").forEach((form) => {
    const passwordInput = form.querySelector("input[name='confirmation_password']");
    const reopenInput = form.querySelector("input[name='dispatch_reopen_authorized']");
    if (passwordInput) passwordInput.value = password;
    if (reopenInput) reopenInput.value = "1";
  });
  panel.querySelectorAll("[data-shipment-dispatch-checkbox]").forEach((checkbox) => {
    checkbox.disabled = false;
  });
  panel.querySelectorAll(".shipment-dispatch-checkbox-row").forEach((row) => {
    row.classList.remove("is-disabled");
  });
  reopenDispatchButton.disabled = true;
  reopenDispatchButton.textContent = "Dispatch stages reopened";
});

document.addEventListener("change", (event) => {
  const dispatchCheckbox = event.target.closest("[data-shipment-dispatch-checkbox]");
  if (!dispatchCheckbox) return;
  const form = dispatchCheckbox.closest(".shipment-dispatch-checkbox-form");
  if (!form) return;
  const statusInput = form.querySelector("input[name='new_status']");
  if (statusInput) {
    statusInput.value = dispatchCheckbox.checked
      ? dispatchCheckbox.dataset.checkedStatus
      : dispatchCheckbox.dataset.uncheckedStatus;
  }
  if (form.requestSubmit) {
    form.requestSubmit();
  } else {
    form.submit();
  }
});

document.addEventListener("submit", (event) => {
  const passwordForm = event.target.closest("[data-confirm-password-submit]");
  if (passwordForm) {
    const message = passwordForm.dataset.confirmPasswordSubmit || "This action cannot be undone.";
    const expectedPassword = passwordForm.dataset.confirmPasswordValue || "Path1234";
    const passwordInput = passwordForm.querySelector("input[name='deletion_password']");
    const confirmationPasswordInput = passwordForm.querySelector("input[name='confirmation_password']");
    if (
      (passwordInput && passwordInput.value === expectedPassword)
      || (confirmationPasswordInput && confirmationPasswordInput.value === expectedPassword)
    ) {
      return;
    }
    if (!window.confirm(message)) {
      event.preventDefault();
      return;
    }
    const password = window.prompt("Enter the confirmation password to continue:");
    if (password !== expectedPassword) {
      event.preventDefault();
      window.alert("Incorrect password. The action was cancelled.");
      return;
    }
    if (passwordInput) passwordInput.value = password;
    if (confirmationPasswordInput) confirmationPasswordInput.value = password;
  }

  const confirmForm = event.target.closest("[data-confirm-submit]");
  if (confirmForm) {
    const submitterMessage = event.submitter?.dataset?.confirmSubmit;
    const message = submitterMessage || confirmForm.dataset.confirmSubmit || "Are you sure?";
    if (!window.confirm(message)) {
      event.preventDefault();
      return;
    }
  }

  const disableOnSubmitForm = event.target.closest("[data-disable-on-submit]");
  if (disableOnSubmitForm) {
    disableOnSubmitForm.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });
    const submitter = event.submitter?.matches?.("button[type='submit']") ? event.submitter : null;
    if (submitter) {
      submitter.dataset.originalText = submitter.textContent;
      submitter.textContent = "Saving...";
    }
  }

  if (event.target.closest("[data-annual-records-table]")) {
    saveAnnualTableScrollState();
  }

  const form = event.target.closest(".member-form");
  if (!form) return;

  const status = form.querySelector("[name='status']")?.value;
  const confirmInput = form.querySelector("[name='confirm_archive']");
  if (status === "Archived" && confirmInput?.value !== "yes") {
    event.preventDefault();
    const confirmed = window.confirm("Are you sure you want to archive this member? Archived members will be hidden from the general list.");
    if (confirmed) {
      confirmInput.value = "yes";
      form.submit();
    }
  }
});

document.querySelectorAll("[data-auto-filter]").forEach((form) => {
  let searchTimer;
  const submitFilters = () => {
    if (form.requestSubmit) {
      form.requestSubmit();
    } else {
      form.submit();
    }
  };

  form.querySelectorAll("select").forEach((field) => {
    field.addEventListener("change", submitFilters);
  });

  form.querySelectorAll("input[type='checkbox']").forEach((field) => {
    field.addEventListener("change", submitFilters);
  });

  const search = form.querySelector("input[name='q']");
  if (search) {
    search.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(submitFilters, 450);
    });
  }

  const year = form.querySelector("input[name='year']");
  if (year) {
    year.addEventListener("input", () => {
      if (year.value && year.value.length < 4) return;
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(submitFilters, 450);
    });
  }
});

document.querySelectorAll("[data-bulk-form], [data-bulk-root]").forEach((form) => {
  const scope = form.dataset.bulkScope ? document.querySelector(form.dataset.bulkScope) : form;
  if (!scope) return;

  const selectAll = scope.querySelector("[data-select-all-members]");
  const checkboxes = Array.from(scope.querySelectorAll("[data-member-select]"));
  const bar = form.matches("[data-bulk-actions]") ? form : form.querySelector("[data-bulk-actions]");
  const selectedCount = form.querySelector("[data-selected-count]");
  const bulkStatus = form.querySelector("[data-bulk-status]");
  const clearButton = form.querySelector("[data-clear-selection]");
  const emailLinks = Array.from(form.querySelectorAll("[data-bulk-email-link]"));

  const syncBulkState = () => {
    const selected = checkboxes.filter((checkbox) => checkbox.checked);
    const count = selected.length;
    if (bar) bar.hidden = count === 0;
    if (selectedCount) {
      selectedCount.textContent = `${count} ${count === 1 ? "member" : "members"} selected`;
    }
    if (bulkStatus && count === 0) bulkStatus.textContent = "";
    if (selectAll) {
      selectAll.checked = count > 0 && count === checkboxes.length;
      selectAll.indeterminate = count > 0 && count < checkboxes.length;
    }
    if (emailLinks.length) {
      const selectedEmails = Array.from(new Set(
        selected
          .map((checkbox) => (checkbox.dataset.memberEmail || "").trim().toLowerCase())
          .filter(Boolean)
      ));
      const gmailUrl = `https://mail.google.com/mail/?view=cm&fs=1&bcc=${encodeURIComponent(selectedEmails.join(","))}`;
      emailLinks.forEach((link) => {
        if (selectedEmails.length) {
          link.href = gmailUrl;
          link.classList.remove("disabled-button");
          link.removeAttribute("aria-disabled");
          link.removeAttribute("tabindex");
        } else {
          link.removeAttribute("href");
          link.classList.add("disabled-button");
          link.setAttribute("aria-disabled", "true");
          link.setAttribute("tabindex", "-1");
        }
      });
    }
  };

  if (selectAll) {
    selectAll.addEventListener("change", () => {
      checkboxes.forEach((checkbox) => {
        checkbox.checked = selectAll.checked;
      });
      syncBulkState();
    });
  }

  checkboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", syncBulkState);
  });

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      checkboxes.forEach((checkbox) => {
        checkbox.checked = false;
      });
      syncBulkState();
    });
  }

  if (form.matches("form")) {
    form.addEventListener("submit", (event) => {
      if (!checkboxes.some((checkbox) => checkbox.checked)) {
        event.preventDefault();
        window.alert(form.dataset.bulkEmptyMessage || "Select at least one member before exporting.");
        if (bulkStatus) bulkStatus.textContent = "";
        return;
      }
      if (bulkStatus) bulkStatus.textContent = form.dataset.bulkSuccessMessage || "Export started.";
    });
  }

  syncBulkState();
});

document.querySelectorAll("[data-bulk-email-link]").forEach((link) => {
  link.addEventListener("click", (event) => {
    if (!link.href || link.getAttribute("aria-disabled") === "true") {
      event.preventDefault();
    }
  });
});

document.querySelectorAll("[data-bulk-stage-form]").forEach((form) => {
  const scope = form.dataset.bulkScope ? document.querySelector(form.dataset.bulkScope) : document;
  if (!scope) return;

  form.addEventListener("submit", (event) => {
    form.querySelectorAll("input[data-generated-member-id]").forEach((input) => input.remove());
    const selected = Array.from(scope.querySelectorAll("[data-member-select]:checked"));
    if (!selected.length) {
      event.preventDefault();
      window.alert(form.dataset.bulkEmptyMessage || "Please select at least one member before applying a bulk action.");
      return;
    }
    selected.forEach((checkbox) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "member_ids";
      input.value = checkbox.value;
      input.dataset.generatedMemberId = "true";
      form.appendChild(input);
    });
    saveAnnualTableScrollState();
  });
});

document.querySelectorAll(".bulk-action-menu").forEach((menu) => {
  const summary = menu.querySelector("summary");
  const panel = menu.querySelector(".bulk-action-panel");
  if (!summary || !panel) return;

  const positionPanel = () => {
    const rect = summary.getBoundingClientRect();
    const panelWidth = Math.min(520, window.innerWidth * 0.82);
    const left = Math.max(12, Math.min(rect.right - panelWidth, window.innerWidth - panelWidth - 12));
    panel.style.left = `${left}px`;
    panel.style.right = "auto";
    panel.style.top = `${Math.min(rect.bottom + 8, window.innerHeight - 120)}px`;
  };

  summary.addEventListener("click", () => {
    window.requestAnimationFrame(() => {
      if (menu.open) positionPanel();
    });
  });
  window.addEventListener("resize", () => {
    if (menu.open) positionPanel();
  });
});

document.querySelectorAll("[data-import-form]").forEach((form) => {
  const fileInput = form.querySelector("[data-import-file]");
  const dropzone = form.querySelector("[data-upload-dropzone]");
  const fileState = form.querySelector("[data-file-state]");
  const validation = form.querySelector("[data-upload-validation]");
  const submitButton = form.querySelector("[data-import-submit]");

  if (!fileInput || !dropzone) return;

  const formatSize = (bytes) => {
    if (!bytes) return "0 KB";
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const setImportState = (file) => {
    const isValid = Boolean(file && file.name.toLowerCase().endsWith(".xlsx"));
    dropzone.classList.toggle("has-file", Boolean(file));
    dropzone.classList.toggle("has-error", Boolean(file) && !isValid);
    if (submitButton) submitButton.disabled = !isValid;

    if (!file) {
      if (fileState) fileState.textContent = "No file selected";
      if (validation) validation.textContent = "";
      return;
    }

    if (fileState) fileState.textContent = `✓ ${file.name} · Size: ${formatSize(file.size)}`;
    if (validation) {
      validation.textContent = isValid ? "✓ File ready for import" : "Only .xlsx files are supported.";
    }
  };

  fileInput.addEventListener("change", () => {
    setImportState(fileInput.files[0]);
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragging");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragging");
    });
  });

  dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    setImportState(file);
  });

  form.addEventListener("submit", (event) => {
    const file = fileInput.files[0];
    if (!file || !file.name.toLowerCase().endsWith(".xlsx")) {
      event.preventDefault();
      setImportState(file);
    }
  });

  setImportState(fileInput.files[0]);
});

const isValidUrlValue = (value) => {
  if (!value) return true;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && Boolean(url.hostname);
  } catch {
    return false;
  }
};

const isValidGoogleMapsValue = (value) => {
  if (!value || !isValidUrlValue(value)) return false;
  const url = new URL(value);
  const host = url.hostname.toLowerCase();
  return (
    host === "maps.google.com" ||
    host === "www.google.com" && url.pathname.startsWith("/maps") ||
    host === "goo.gl" && url.pathname.startsWith("/maps") ||
    host === "maps.app.goo.gl"
  );
};

const isValidSessionDateValue = (value) => {
  return !getSessionDateError(value);
};

const getSessionDateError = (value) => {
  const match = value.trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return value.trim() ? "Date is incomplete" : "";
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  const currentYear = new Date().getFullYear();
  if (day < 1 || day > 31) return "Day is wrong";
  if (month < 1 || month > 12) return "Month is wrong";
  if (year < currentYear) return "Year is wrong";
  return "";
};

const formatSessionDateInput = (value) => {
  const cleaned = value.replace(/[^\d/]/g, "");
  if (cleaned.includes("/")) {
    const rawParts = cleaned.split("/").slice(0, 3);
    const daySource = (rawParts[0] || "").replace(/\D/g, "");
    const day = daySource.slice(0, 2);
    const dayOverflow = daySource.slice(2);
    const monthSource = `${dayOverflow}${(rawParts[1] || "").replace(/\D/g, "")}`;
    const month = monthSource.slice(0, 2);
    const monthOverflow = monthSource.slice(2);
    const year = `${monthOverflow}${(rawParts[2] || "").replace(/\D/g, "")}`.slice(0, 4);
    const firstSlashTyped = rawParts.length > 1;
    const secondSlashTyped = cleaned.indexOf("/") !== cleaned.lastIndexOf("/");

    let formatted = firstSlashTyped && day.length === 1 ? `0${day}` : day;
    if (firstSlashTyped) formatted += "/";
    if (month) {
      formatted += (secondSlashTyped || year) && month.length === 1 ? `0${month}` : month;
    }
    if (secondSlashTyped || year) formatted += "/";
    if (year) formatted += year;
    return formatted.slice(0, 10);
  }
  const digits = value.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  const day = digits.slice(0, 2);
  if (digits.length <= 4) return `${day}/${digits.slice(2)}`;
  return `${day}/${digits.slice(2, 4)}/${digits.slice(4)}`;
};

const formatTimeInput = (value) => {
  const digits = value.replace(/\D/g, "").slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}:${digits.slice(2)}`;
};

const isValidTimeInput = (value) => {
  if (!value) return true;
  const match = value.match(/^(\d{2}):(\d{2})$/);
  if (!match) return false;
  const hours = Number.parseInt(match[1], 10);
  const minutes = Number.parseInt(match[2], 10);
  return hours >= 0 && hours <= 24 && minutes >= 0 && minutes <= 59;
};

const syncTimeRangeError = (input) => {
  const wrapper = input.closest("[data-time-range-stack]");
  const error = wrapper?.querySelector("[data-time-error]");
  if (!error) return;
  const hasError = Array.from(wrapper.querySelectorAll("[data-time-input]")).some((field) => !isValidTimeInput(field.value));
  error.textContent = hasError ? "Wrong time" : "";
};

const initTimeInputs = (root = document) => {
  root.querySelectorAll("[data-time-input]").forEach((input) => {
    if (input.dataset.timeInitialized === "true") return;
    input.dataset.timeInitialized = "true";
    input.addEventListener("input", () => {
      const formatted = formatTimeInput(input.value);
      if (input.value !== formatted) input.value = formatted;
      syncTimeRangeError(input);
      syncSupervisorRoleFee(input.closest("[data-supervisor-row]"), { forceEmpty: true });
      syncDeviceDep(staffAssignmentRow(input), { forceEmpty: true });
    });
    input.addEventListener("blur", () => {
      const digits = input.value.replace(/\D/g, "");
      if (digits.length > 0 && digits.length <= 2) {
        input.value = `${digits.padStart(2, "0")}:00`;
      }
      syncTimeRangeError(input);
      syncSupervisorRoleFee(input.closest("[data-supervisor-row]"), { forceEmpty: true });
      syncDeviceDep(staffAssignmentRow(input), { forceEmpty: true });
    });
    input.addEventListener("keydown", (event) => {
      const allowedKeys = [
        "Backspace",
        "Delete",
        "Tab",
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
      ];
      if (event.ctrlKey || event.metaKey || allowedKeys.includes(event.key)) return;
      if (!/^[\d:]$/.test(event.key)) event.preventDefault();
    });
    syncTimeRangeError(input);
  });
};

document.addEventListener("click", (event) => {
  const addButton = event.target.closest("[data-add-time-range]");
  if (addButton) {
    if (rowFeesAreLocked(staffAssignmentRow(addButton))) return;
    const row = addButton.closest("[data-time-range-row]");
    const stack = addButton.closest("[data-time-range-stack]");
    if (!row || !stack) return;
    const clone = row.cloneNode(true);
    clone.querySelectorAll("input").forEach((input) => {
      input.value = "";
      input.dataset.timeInitialized = "";
    });
    const button = clone.querySelector("[data-add-time-range]");
    if (button) {
      button.className = "time-range-remove-button";
      button.removeAttribute("data-add-time-range");
      button.setAttribute("data-remove-time-range", "");
      button.setAttribute("aria-label", "Remove time range");
      button.textContent = "×";
    }
    stack.insertBefore(clone, stack.querySelector("[data-time-error]"));
    initTimeInputs(clone);
    syncSupervisorRoleFee(stack.closest("[data-supervisor-row]"), { forceEmpty: true });
    syncDeviceDep(staffAssignmentRow(stack), { forceEmpty: true });
    clone.querySelector("input")?.focus();
  }

  const removeButton = event.target.closest("[data-remove-time-range]");
  if (removeButton) {
    if (rowFeesAreLocked(staffAssignmentRow(removeButton))) return;
    const stack = removeButton.closest("[data-time-range-stack]");
    removeButton.closest("[data-time-range-row]")?.remove();
    stack?.querySelector("[data-time-input]") && syncTimeRangeError(stack.querySelector("[data-time-input]"));
    syncSupervisorRoleFee(stack?.closest("[data-supervisor-row]"), { forceEmpty: true });
    syncDeviceDep(staffAssignmentRow(stack), { forceEmpty: true });
  }
});

let pendingYearChangeForm = null;

const sessionDateYear = (value) => {
  const match = (value || "").match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  return match ? match[3] : "";
};

const yearChangeModal = document.getElementById("year-change-confirmation");
document.querySelectorAll("[data-year-change-cancel]").forEach((button) => {
  button.addEventListener("click", () => {
    pendingYearChangeForm = null;
    closeModal(yearChangeModal);
  });
});

document.querySelector("[data-year-change-continue]")?.addEventListener("click", () => {
  const form = pendingYearChangeForm;
  pendingYearChangeForm = null;
  closeModal(yearChangeModal);
  if (form) {
    form.dataset.yearChangeConfirmed = "true";
    form.requestSubmit();
  }
});

document.querySelectorAll("[data-exam-session-form]").forEach((form) => {
  const submitButton = form.querySelector("[data-exam-session-submit]");
  const onsiteFields = form.querySelectorAll("[data-onsite-field]");
  const locationInput = form.querySelector("[name='location_url']");
  const fullAddressInput = form.querySelector("[name='full_address_google_maps']");
  const cityInput = form.querySelector("[name='city']");
  const provinceInput = form.querySelector("[name='province']");
  const dateInput = form.querySelector("[name='session_date']");
  const dateError = form.querySelector("[data-date-error]");
  const shiftInputs = Array.from(form.querySelectorAll("[data-exam-shift-option]"));
  const allDayShift = shiftInputs.find((input) => input.value === "All day");
  const partialShiftValues = ["Morning", "Afternoon", "Evening"];
  const partialShifts = shiftInputs.filter((input) => partialShiftValues.includes(input.value));

  const syncExamShiftOptions = (changedInput = null) => {
    if (!allDayShift) return;
    if (changedInput === allDayShift && allDayShift.checked) {
      partialShifts.forEach((input) => {
        input.checked = false;
        input.disabled = true;
      });
      allDayShift.disabled = false;
      return;
    }

    const selectedPartialShifts = partialShifts.filter((input) => input.checked);
    if (selectedPartialShifts.length === partialShifts.length && partialShifts.length > 0) {
      partialShifts.forEach((input) => {
        input.checked = false;
        input.disabled = true;
      });
      allDayShift.checked = true;
      allDayShift.disabled = false;
      return;
    }

    if (selectedPartialShifts.length > 0) {
      allDayShift.checked = false;
      allDayShift.disabled = true;
      partialShifts.forEach((input) => {
        input.disabled = false;
      });
      return;
    }

    allDayShift.disabled = false;
    partialShifts.forEach((input) => {
      input.disabled = allDayShift.checked;
    });
  };

  shiftInputs.forEach((input) => {
    input.addEventListener("change", () => syncExamShiftOptions(input));
  });

  const syncExamSessionForm = () => {
    const examSessionName = form.querySelector("[name='exam_session_name']")?.value.trim() || "";
    const category = form.querySelector("[name='category']")?.value || "";
    const status = form.querySelector("[name='status']")?.value;
    const dateValue = form.querySelector("[name='session_date']")?.value || "";
    const modules = form.querySelectorAll("[name='modules']:checked");
    const selectedFormat = form.querySelector("[name='format']:checked")?.value || "";
    const detailsValue = form.querySelector("[name='details_url']")?.value || "";
    const hasExamCentreFields = selectedFormat === "Onsite" || selectedFormat === "Online at exam centre";

    onsiteFields.forEach((field) => {
      field.hidden = !hasExamCentreFields;
    });
    if (!hasExamCentreFields) {
      if (locationInput) locationInput.value = "";
      if (fullAddressInput) fullAddressInput.value = "";
      if (cityInput) cityInput.value = "";
      if (provinceInput) provinceInput.value = "";
    }

    const dateErrorMessage = getSessionDateError(dateValue);
    if (dateError) dateError.textContent = dateErrorMessage;
    const valid = Boolean(examSessionName) &&
      Boolean(category) &&
      Boolean(status) &&
      !dateErrorMessage &&
      modules.length > 0 &&
      Boolean(selectedFormat) &&
      isValidUrlValue(detailsValue);

    if (submitButton) submitButton.disabled = !valid;
  };

  form.addEventListener("input", syncExamSessionForm);
  form.addEventListener("change", syncExamSessionForm);
  form.addEventListener("submit", (event) => {
    if (form.dataset.yearChangeConfirmed === "true") {
      delete form.dataset.yearChangeConfirmed;
      return;
    }
    const originalYear = form.dataset.originalSessionYear || "";
    const currentYear = sessionDateYear(dateInput?.value || "");
    if (!originalYear || !currentYear || originalYear === currentYear) return;
    event.preventDefault();
    pendingYearChangeForm = form;
    openModal("year-change-confirmation");
  });
  if (dateInput) {
    dateInput.addEventListener("keydown", (event) => {
      const allowedKeys = [
        "Backspace",
        "Delete",
        "Tab",
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
      ];
      if (event.ctrlKey || event.metaKey || allowedKeys.includes(event.key)) return;
      if (!/^[\d/]$/.test(event.key)) event.preventDefault();
    });
    dateInput.addEventListener("input", () => {
      const formatted = formatSessionDateInput(dateInput.value);
      if (dateInput.value !== formatted) dateInput.value = formatted;
      syncExamSessionForm();
    });
  }
  syncExamShiftOptions();
  syncExamSessionForm();
});

document.querySelectorAll("[data-toggle-section]").forEach((button) => {
  const target = document.getElementById(button.dataset.toggleSection);
  if (!target) return;

  const syncButton = () => {
    const isExpanded = !target.hidden;
    button.setAttribute("aria-expanded", String(isExpanded));
    button.textContent = isExpanded ? "Hide" : "Show";
  };

  button.addEventListener("click", () => {
    target.hidden = !target.hidden;
    syncButton();
  });

  syncButton();
});

let pendingMonthlyResetForm = null;

document.querySelectorAll("[data-reset-monthly-form]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (form.dataset.resetConfirmed === "true") {
      delete form.dataset.resetConfirmed;
      return;
    }
    event.preventDefault();
    pendingMonthlyResetForm = form;
    openModal("reset-monthly-confirmation");
  });
});

document.querySelectorAll("[data-reset-monthly-cancel]").forEach((button) => {
  button.addEventListener("click", () => {
    pendingMonthlyResetForm = null;
    closeModal(document.getElementById("reset-monthly-confirmation"));
  });
});

document.querySelector("[data-reset-monthly-confirm]")?.addEventListener("click", () => {
  const form = pendingMonthlyResetForm;
  pendingMonthlyResetForm = null;
  closeModal(document.getElementById("reset-monthly-confirmation"));
  if (form) {
    form.dataset.resetConfirmed = "true";
    form.requestSubmit();
  }
});

const commutingFieldNames = (row, fallbackName = "") => {
  const sectionKey = row?.dataset.sectionKey || "";
  const kmName = row?.querySelector("[data-km-input]")?.name || "";
  const baseName = fallbackName || (sectionKey && kmName.startsWith(`${sectionKey}_km_`)
    ? kmName.replace(`${sectionKey}_km_`, `${sectionKey}_commuting_`)
    : "");
  return {
    value: baseName,
    currency: baseName ? baseName.replace("_commuting_", "_commuting_currency_") : "",
    base: baseName ? baseName.replace("_commuting_", "_commuting_base_value_") : "",
    unit: baseName ? baseName.replace("_commuting_", "_commuting_unit_") : "",
  };
};

const renderCommutingCalculatedField = (row, fallbackName = "") => {
  const names = commutingFieldNames(row, fallbackName);
  const valueInput = document.createElement("input");
  valueInput.type = "hidden";
  valueInput.name = names.value || "";
  valueInput.setAttribute("data-commuting-input", "");

  const currencyInput = document.createElement("input");
  currencyInput.type = "hidden";
  currencyInput.name = names.currency || "";
  currencyInput.setAttribute("data-commuting-currency-input", "");

  const baseInput = document.createElement("input");
  baseInput.type = "hidden";
  baseInput.name = names.base || "";
  baseInput.setAttribute("data-commuting-base-input", "");

  const unitInput = document.createElement("input");
  unitInput.type = "hidden";
  unitInput.name = names.unit || "";
  unitInput.setAttribute("data-commuting-unit-input", "");

  const display = document.createElement("span");
  display.className = "calculated-role-fee";
  display.setAttribute("data-commuting-display", "");
  display.textContent = "-";

  return [valueInput, currencyInput, baseInput, unitInput, display];
};

const replaceStaffCardFieldValue = (cell, ...nodes) => {
  if (!cell) return;
  const label = cell.querySelector(":scope > .staff-card-field-label");
  if (label) {
    cell.replaceChildren(label, ...nodes);
  } else {
    cell.replaceChildren(...nodes);
  }
};

const rowHasKmEnabled = (row) => Boolean(row?.querySelector("[data-km-input]"));

const syncRemoteKmMutualExclusion = (row) => {
  if (!row) return;
  const remoteCheckbox = row.querySelector("[data-supervisor-remote-checkbox]");
  const kmCheckbox = row.querySelector("[data-enable-km]");
  const kmEnabled = rowHasKmEnabled(row);
  if (remoteCheckbox) {
    remoteCheckbox.disabled = kmEnabled;
  }
  if (kmCheckbox) {
    kmCheckbox.disabled = Boolean(remoteCheckbox?.checked);
  }
};

document.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-enable-km]");
  if (!checkbox || !checkbox.checked) return;
  if (rowFeesAreLocked(staffAssignmentRow(checkbox))) {
    checkbox.checked = false;
    return;
  }
  const field = checkbox.closest("[data-km-field]");
  if (!field) return;
  const row = staffAssignmentRow(field);
  const remoteCheckbox = row?.querySelector("[data-supervisor-remote-checkbox]");
  if (remoteCheckbox) remoteCheckbox.checked = false;
  const input = document.createElement("input");
  input.className = "km-input";
  input.name = checkbox.dataset.kmName || "";
  input.dataset.kmInput = "";
  input.dataset.kmName = input.name;
  input.inputMode = "numeric";
  input.pattern = "[0-9]*";
  input.min = "0";
  input.step = "1";
  input.placeholder = "Km.";
  input.setAttribute("data-integer-input", "");
  input.addEventListener("input", () => {
    syncKmDisableButton(input);
    syncCommuting(row, { forceEmpty: true });
    syncFuelVehicleCells(row);
    syncFuel(row, { forceEmpty: true });
    syncVehicleDep(row, { forceEmpty: true });
  });
  const removeButton = document.createElement("button");
  removeButton.className = "km-disable-button";
  removeButton.type = "button";
  removeButton.setAttribute("data-disable-km", "");
  removeButton.setAttribute("aria-label", "Disable Km");
  removeButton.textContent = "×";
  field.replaceChildren(input, removeButton);
  const commutingCell = row?.querySelector("[data-commuting-cell]");
  const commutingName = commutingCell?.querySelector("[data-commuting-dash]")?.dataset.commutingName || "";
  if (commutingCell) {
    replaceStaffCardFieldValue(commutingCell, ...renderCommutingCalculatedField(row, commutingName));
  }
  initIntegerInputs(field);
  syncCommuting(row, { forceEmpty: true });
  syncFuelVehicleCells(row);
  syncRemoteKmMutualExclusion(row);
  input.focus();
});

document.addEventListener("change", (event) => {
  const remoteCheckbox = event.target.closest("[data-supervisor-remote-checkbox]");
  if (!remoteCheckbox) return;
  const row = staffAssignmentRow(remoteCheckbox);
  if (remoteCheckbox.checked) {
    resetKmFieldToCheckbox(row);
  }
  syncRemoteKmMutualExclusion(row);
});

const syncKmDisableButton = (input) => {
  const button = input.closest("[data-km-field]")?.querySelector("[data-disable-km]");
  if (!button) return;
  button.hidden = input.value.trim() !== "";
};

const resetKmFieldToCheckbox = (row) => {
  const field = row?.querySelector("[data-km-field]");
  const input = field?.querySelector("[data-km-input]");
  if (!field || !input) return;
  const label = document.createElement("label");
  label.className = "km-checkbox-label";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.setAttribute("data-enable-km", "");
  checkbox.dataset.kmName = input.dataset.kmName || input.name || "";
  label.appendChild(checkbox);
  field.replaceChildren(label);
  const commutingCell = row?.querySelector("[data-commuting-cell]");
  const commutingInput = commutingCell?.querySelector("[data-commuting-input]");
  if (commutingCell && commutingInput) {
    const dash = document.createElement("span");
    dash.className = "assignment-disabled-dash";
    dash.setAttribute("data-commuting-dash", "");
    dash.dataset.commutingName = commutingInput.name || "";
    dash.textContent = "-";
    replaceStaffCardFieldValue(commutingCell, dash);
  }
  syncCommuting(row, { forceEmpty: true });
  syncFuelVehicleCells(row);
  syncRemoteKmMutualExclusion(row);
};

document.addEventListener("input", (event) => {
  const input = event.target.closest("[data-km-input]");
  if (input) {
    syncKmDisableButton(input);
    syncCommuting(staffAssignmentRow(input), { forceEmpty: true });
    syncFuelVehicleCells(staffAssignmentRow(input));
    syncFuel(staffAssignmentRow(input), { forceEmpty: true });
    syncVehicleDep(staffAssignmentRow(input), { forceEmpty: true });
  }
  const costInput = event.target.closest(".assignment-cost-input");
  if (costInput) {
    if (costInput.matches("[data-role-fee-input]")) syncSeniority(staffAssignmentRow(costInput));
    syncAssignmentTotalFee(staffAssignmentRow(costInput));
  }
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-disable-km]");
  if (!button) return;
  if (rowFeesAreLocked(staffAssignmentRow(button))) return;
  const field = button.closest("[data-km-field]");
  const input = field?.querySelector("[data-km-input]");
  if (!field || !input || input.value.trim() !== "") return;
  resetKmFieldToCheckbox(staffAssignmentRow(field));
});

const selectedRowTeamMemberHasCar = (row) => {
  const select = row?.querySelector("[data-team-member-select]");
  const option = select ? selectedTeamMemberOption(select) : null;
  return option?.dataset.hasCar === "true";
};

const fuelVehicleNames = (row) => {
  const fuelCell = row?.querySelector("[data-fuel-cell]");
  const vehicleCell = row?.querySelector("[data-vehicle-cell]");
  return {
    fuel: fuelCell?.querySelector("[data-fuel-input]")?.name
      || fuelCell?.querySelector("[data-fuel-name]")?.dataset.fuelName
      || "",
    vehicle: vehicleCell?.querySelector("[data-vehicle-input]")?.name
      || vehicleCell?.querySelector("[data-vehicle-name]")?.dataset.vehicleName
      || fuelCell?.querySelector("[data-vehicle-name]")?.dataset.vehicleName
      || "",
  };
};

const fuelFieldNames = (baseName = "") => ({
  enabled: baseName ? baseName.replace("_fuel_", "_fuel_enabled_") : "",
  value: baseName || "",
  currency: baseName ? baseName.replace("_fuel_", "_fuel_currency_") : "",
  base: baseName ? baseName.replace("_fuel_", "_fuel_base_value_") : "",
  unit: baseName ? baseName.replace("_fuel_", "_fuel_unit_") : "",
});

const vehicleDepFieldNames = (baseName = "") => ({
  value: baseName || "",
  currency: baseName ? baseName.replace("_vehicle_dep_", "_vehicle_dep_currency_") : "",
  base: baseName ? baseName.replace("_vehicle_dep_", "_vehicle_dep_base_value_") : "",
  unit: baseName ? baseName.replace("_vehicle_dep_", "_vehicle_dep_unit_") : "",
});

const renderDisabledAssignmentDash = (name, dataName) => {
  const dash = document.createElement("span");
  dash.className = "assignment-disabled-dash";
  dash.textContent = "-";
  dash.setAttribute(dataName, "");
  if (dataName === "data-fuel-dash") {
    dash.dataset.fuelName = name.fuel || "";
    dash.dataset.vehicleName = name.vehicle || "";
  } else {
    dash.dataset.vehicleName = name.vehicle || "";
  }
  return dash;
};

const renderFuelVehicleCheckbox = (names) => {
  const label = document.createElement("label");
  label.className = "fuel-checkbox-label";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.setAttribute("data-enable-fuel-vehicle", "");
  checkbox.dataset.fuelName = names.fuel || "";
  checkbox.dataset.vehicleName = names.vehicle || "";
  label.appendChild(checkbox);
  return label;
};

const renderFuelCalculatedField = (baseName = "") => {
  const names = fuelFieldNames(baseName);
  const enabledInput = document.createElement("input");
  enabledInput.type = "hidden";
  enabledInput.name = names.enabled;
  enabledInput.value = "1";
  enabledInput.setAttribute("data-fuel-enabled-input", "");

  const valueInput = document.createElement("input");
  valueInput.type = "hidden";
  valueInput.name = names.value;
  valueInput.setAttribute("data-fuel-input", "");

  const currencyInput = document.createElement("input");
  currencyInput.type = "hidden";
  currencyInput.name = names.currency;
  currencyInput.setAttribute("data-fuel-currency-input", "");

  const baseInput = document.createElement("input");
  baseInput.type = "hidden";
  baseInput.name = names.base;
  baseInput.setAttribute("data-fuel-base-input", "");

  const unitInput = document.createElement("input");
  unitInput.type = "hidden";
  unitInput.name = names.unit;
  unitInput.setAttribute("data-fuel-unit-input", "");

  const display = document.createElement("span");
  display.className = "calculated-role-fee";
  display.setAttribute("data-fuel-display", "");
  display.textContent = "-";

  return [enabledInput, valueInput, currencyInput, baseInput, unitInput, display];
};

const renderVehicleDepCalculatedField = (baseName = "") => {
  const names = vehicleDepFieldNames(baseName);
  const valueInput = document.createElement("input");
  valueInput.type = "hidden";
  valueInput.name = names.value;
  valueInput.setAttribute("data-vehicle-input", "");

  const currencyInput = document.createElement("input");
  currencyInput.type = "hidden";
  currencyInput.name = names.currency;
  currencyInput.setAttribute("data-vehicle-currency-input", "");

  const baseInput = document.createElement("input");
  baseInput.type = "hidden";
  baseInput.name = names.base;
  baseInput.setAttribute("data-vehicle-base-input", "");

  const unitInput = document.createElement("input");
  unitInput.type = "hidden";
  unitInput.name = names.unit;
  unitInput.setAttribute("data-vehicle-unit-input", "");

  const display = document.createElement("span");
  display.className = "calculated-role-fee";
  display.setAttribute("data-vehicle-display", "");
  display.textContent = "-";

  return [valueInput, currencyInput, baseInput, unitInput, display];
};

const renderAssignmentCostInput = (name, placeholder, dataAttribute) => {
  const input = document.createElement("input");
  input.className = "assignment-cost-input";
  input.name = name || "";
  input.placeholder = placeholder;
  input.setAttribute(dataAttribute, "");
  return input;
};

const assignmentFieldName = (row, fieldName) => {
  const overrideName = row?.querySelector("[data-manual-fee-override]")?.name || "";
  return overrideName ? overrideName.replace("_manual_fee_override_", `_${fieldName}_`) : "";
};

const manualFeeCurrencyOptions = ["ARS", "EUR", "GBP", "USD", "UYU"];

const normalizeManualFeeAmountInput = (input) => {
  input.value = input.value.replace(/\./g, "").replace(/[^0-9,]/g, "");
  const commaIndex = input.value.indexOf(",");
  if (commaIndex !== -1) {
    input.value = `${input.value.slice(0, commaIndex + 1)}${input.value.slice(commaIndex + 1).replace(/,/g, "")}`;
  }
};

const roundManualFeeAmountInput = (input) => {
  normalizeManualFeeAmountInput(input);
  const value = input.value.trim();
  if (!value) return;
  const parsed = Number.parseFloat(value.replace(",", "."));
  if (!Number.isFinite(parsed) || parsed < 0) {
    input.value = "";
    return;
  }
  const integerPart = Math.floor(parsed);
  const decimalPart = parsed - integerPart;
  input.value = String(decimalPart > 0.5 ? integerPart + 1 : integerPart);
};

const amountWithoutCurrency = (value) => {
  const amount = String(value || "").replace(/^\s*[A-Z]{3}\b\s*/, "").trim();
  const parsed = Number.parseFloat(amount.replace(/\./g, "").replace(",", "."));
  if (!Number.isFinite(parsed)) return amount.replace(/[^0-9,]/g, "");
  const integerPart = Math.floor(parsed);
  const decimalPart = parsed - integerPart;
  return String(decimalPart > 0.5 ? integerPart + 1 : integerPart);
};

const manualFeeCurrencyForField = (valueInput, currencyInput) => (
  currencyInput?.value
  || currencyFromFeeValue(valueInput?.value || "")
  || "ARS"
);

const updateManualFeeValue = (row, config, valueInput, currencyInput, display, currencySelect, amountInput) => {
  if (!valueInput || !display || !currencySelect || !amountInput) return;
  const amount = amountInput.value.trim();
  const currency = currencySelect.value || "ARS";
  valueInput.value = amount ? `${currency} ${amount}` : "";
  if (currencyInput) currencyInput.value = amount ? currency : "";
  display.textContent = valueInput.value || "-";
  display.title = valueInput.value || "";
  if (config.appliedAttribute) {
    const appliedInput = row.querySelector(`[${config.appliedAttribute}]`);
    if (appliedInput) appliedInput.value = amount ? "1" : "";
  }
  syncAssignmentTotalFee(row);
};

const ensureHiddenInput = (cell, name, attributeName, value = "") => {
  let input = cell?.querySelector(`[${attributeName}]`);
  if (input) return input;
  input = document.createElement("input");
  input.type = "hidden";
  input.name = name || "";
  input.value = value;
  input.setAttribute(attributeName, "");
  cell?.prepend(input);
  return input;
};

const ensureFeeDisplay = (cell, attributeName, value = "-") => {
  let display = cell?.querySelector(`[${attributeName}]`);
  if (display) return display;
  display = document.createElement("span");
  display.className = "calculated-role-fee";
  display.setAttribute(attributeName, "");
  display.textContent = value || "-";
  cell?.append(display);
  return display;
};

const ensureManualFeeField = (row, config) => {
  const cell = row?.querySelector(config.cellSelector);
  if (!cell) return null;
  if (config.enabledField) {
    ensureHiddenInput(cell, assignmentFieldName(row, config.enabledField), config.enabledAttribute, "1").value = "1";
  }
  const valueInput = ensureHiddenInput(cell, assignmentFieldName(row, config.field), config.valueAttribute);
  const currencyInput = config.currencyField
    ? ensureHiddenInput(cell, assignmentFieldName(row, config.currencyField), config.currencyAttribute)
    : null;
  if (config.baseField) ensureHiddenInput(cell, assignmentFieldName(row, config.baseField), config.baseAttribute);
  if (config.unitField) ensureHiddenInput(cell, assignmentFieldName(row, config.unitField), config.unitAttribute);
  const display = ensureFeeDisplay(cell, config.displayAttribute, valueInput.value || "-");
  const dash = cell.querySelector(".assignment-disabled-dash");
  if (dash) dash.remove();
  return { valueInput, currencyInput, display };
};

const createManualFeeEditor = (row, config) => {
  const field = ensureManualFeeField(row, config);
  if (!field) return;
  const { valueInput, currencyInput, display } = field;
  valueInput.type = "hidden";
  valueInput.classList.remove("assignment-cost-input", "manual-fee-input", "is-locked");
  let editor = display.parentElement?.querySelector(`[data-manual-fee-editor="${config.field}"]`);
  if (!editor) {
    editor = document.createElement("span");
    editor.className = "manual-fee-editor";
    editor.dataset.manualFeeEditor = config.field;
    const currencySelect = document.createElement("select");
    currencySelect.className = "manual-fee-currency-select";
    currencySelect.setAttribute("aria-label", `${config.placeholder} currency`);
    manualFeeCurrencyOptions.forEach((currency) => {
      const option = document.createElement("option");
      option.value = currency;
      option.textContent = currency;
      currencySelect.append(option);
    });
    const amountInput = document.createElement("input");
    amountInput.type = "text";
    amountInput.className = "assignment-cost-input manual-fee-input";
    amountInput.placeholder = config.placeholder;
    amountInput.inputMode = "decimal";
    amountInput.pattern = "[0-9]+(,[0-9]+)?";
    amountInput.setAttribute("aria-label", config.placeholder);
    editor.append(currencySelect, amountInput);
    display.after(editor);
    const syncEditor = () => updateManualFeeValue(row, config, valueInput, currencyInput, display, currencySelect, amountInput);
    currencySelect.addEventListener("change", syncEditor);
    amountInput.addEventListener("input", () => {
      normalizeManualFeeAmountInput(amountInput);
      syncEditor();
    });
    amountInput.addEventListener("blur", () => {
      roundManualFeeAmountInput(amountInput);
      syncEditor();
    });
  }
  const currencySelect = editor.querySelector(".manual-fee-currency-select");
  const amountInput = editor.querySelector(".manual-fee-input");
  if (currencySelect) currencySelect.value = manualFeeCurrencyForField(valueInput, currencyInput);
  if (amountInput) amountInput.value = amountWithoutCurrency(valueInput.value);
  display.hidden = true;
  editor.hidden = false;
  if (currencyInput && valueInput.value) currencyInput.value = currencySelect?.value || currencyInput.value;
};

const manualFeeConfigs = [
  {
    cellSelector: "td:nth-child(7)",
    field: "role_fee",
    valueAttribute: "data-role-fee-input",
    currencyField: "role_fee_currency",
    currencyAttribute: "data-role-fee-currency-input",
    baseField: "role_fee_base_value",
    baseAttribute: "data-role-fee-base-input",
    unitField: "role_fee_unit",
    unitAttribute: "data-role-fee-unit-input",
    displayAttribute: "data-role-fee-display",
    placeholder: "Role fee",
  },
  {
    cellSelector: "td:nth-child(8)",
    field: "device_dep",
    valueAttribute: "data-device-dep-input",
    currencyField: "device_dep_currency",
    currencyAttribute: "data-device-dep-currency-input",
    baseField: "device_dep_base_value",
    baseAttribute: "data-device-dep-base-input",
    unitField: "device_dep_unit",
    unitAttribute: "data-device-dep-unit-input",
    displayAttribute: "data-device-dep-display",
    placeholder: "Device dep.",
  },
  {
    cellSelector: "[data-commuting-cell]",
    field: "commuting",
    valueAttribute: "data-commuting-input",
    currencyField: "commuting_currency",
    currencyAttribute: "data-commuting-currency-input",
    baseField: "commuting_base_value",
    baseAttribute: "data-commuting-base-input",
    unitField: "commuting_unit",
    unitAttribute: "data-commuting-unit-input",
    displayAttribute: "data-commuting-display",
    placeholder: "Commuting",
  },
  {
    cellSelector: "[data-fuel-cell]",
    field: "fuel",
    valueAttribute: "data-fuel-input",
    enabledField: "fuel_enabled",
    enabledAttribute: "data-fuel-enabled-input",
    currencyField: "fuel_currency",
    currencyAttribute: "data-fuel-currency-input",
    baseField: "fuel_base_value",
    baseAttribute: "data-fuel-base-input",
    unitField: "fuel_unit",
    unitAttribute: "data-fuel-unit-input",
    displayAttribute: "data-fuel-display",
    placeholder: "Fuel",
  },
  {
    cellSelector: "[data-vehicle-cell]",
    field: "vehicle_dep",
    valueAttribute: "data-vehicle-input",
    currencyField: "vehicle_dep_currency",
    currencyAttribute: "data-vehicle-currency-input",
    baseField: "vehicle_dep_base_value",
    baseAttribute: "data-vehicle-base-input",
    unitField: "vehicle_dep_unit",
    unitAttribute: "data-vehicle-unit-input",
    displayAttribute: "data-vehicle-display",
    placeholder: "Vehicle dep.",
  },
  {
    cellSelector: "td:nth-child(12)",
    field: "seniority_fee",
    valueAttribute: "data-seniority-input",
    currencyField: "seniority_currency",
    currencyAttribute: "data-seniority-currency-input",
    displayAttribute: "data-seniority-display",
    appliedAttribute: "data-seniority-applied-input",
    placeholder: "Seniority",
  },
];

const enableManualFeeOverride = (row) => {
  if (!row || rowFeesAreLocked(row)) return;
  const overrideInput = row.querySelector("[data-manual-fee-override]");
  if (overrideInput) overrideInput.value = "1";
  row.classList.add("is-manual-fee-editing");
  manualFeeConfigs.forEach((config) => createManualFeeEditor(row, config));
  syncEditFeesButton(row);
  syncAssignmentTotalFee(row);
};

const saveManualFeeOverride = (row) => {
  if (!row || rowFeesAreLocked(row)) return;
  manualFeeConfigs.forEach((config) => {
    const field = ensureManualFeeField(row, config);
    if (!field) return;
    const { valueInput, currencyInput, display } = field;
    const editor = display.parentElement?.querySelector(`[data-manual-fee-editor="${config.field}"]`);
    if (editor) {
      const currencySelect = editor.querySelector(".manual-fee-currency-select");
      const amountInput = editor.querySelector(".manual-fee-input");
      if (amountInput) roundManualFeeAmountInput(amountInput);
      updateManualFeeValue(row, config, valueInput, currencyInput, display, currencySelect, amountInput);
      display.hidden = false;
      editor.hidden = true;
    }
    if (config.appliedAttribute) {
      const appliedInput = row.querySelector(`[${config.appliedAttribute}]`);
      if (appliedInput) appliedInput.value = valueInput.value.trim() ? "1" : "";
    }
  });
  row.classList.remove("is-manual-fee-editing");
  row.classList.add("has-saved-manual-fees");
  syncEditFeesButton(row);
  syncAssignmentTotalFee(row);
};

const resetManualFeeOverride = (row) => {
  if (!row || rowFeesAreLocked(row)) return;
  const overrideInput = row.querySelector("[data-manual-fee-override]");
  if (overrideInput) overrideInput.value = "";
  row.classList.remove("is-manual-fee-editing", "has-saved-manual-fees");
  row.querySelectorAll("[data-manual-fee-editor]").forEach((editor) => editor.remove());
  row.querySelectorAll(".calculated-role-fee[hidden]").forEach((display) => {
    display.hidden = false;
  });
  row.querySelectorAll(".manual-fee-input").forEach((input) => {
    input.readOnly = false;
    input.classList.remove("is-locked", "manual-fee-input");
  });
  resetFuelVehicleActivation(row);
  syncLiveFeeCalculations(row, { forceEmpty: true });
  syncEditFeesButton(row);
};

const enableFuelVehicleInputs = (row) => {
  const fuelCell = row?.querySelector("[data-fuel-cell]");
  const vehicleCell = row?.querySelector("[data-vehicle-cell]");
  if (!fuelCell || !vehicleCell) return;
  const names = fuelVehicleNames(row);
  replaceStaffCardFieldValue(fuelCell, ...renderFuelCalculatedField(names.fuel));
  replaceStaffCardFieldValue(vehicleCell, ...renderVehicleDepCalculatedField(names.vehicle));
  syncFuel(row, { forceEmpty: true });
  syncVehicleDep(row, { forceEmpty: true });
};

const resetFuelVehicleActivation = (row) => {
  const fuelCell = row?.querySelector("[data-fuel-cell]");
  const vehicleCell = row?.querySelector("[data-vehicle-cell]");
  if (!fuelCell || !vehicleCell) return;
  const names = fuelVehicleNames(row);
  const kmInput = row.querySelector("[data-km-input]");
  const kmValue = Number.parseInt(kmInput?.value || "", 10);
  const canActivateFuel = Boolean(kmInput) && Number.isInteger(kmValue) && kmValue >= 60 && selectedRowTeamMemberHasCar(row);
  replaceStaffCardFieldValue(
    fuelCell,
    canActivateFuel
      ? renderFuelVehicleCheckbox(names)
      : renderDisabledAssignmentDash(names, "data-fuel-dash")
  );
  replaceStaffCardFieldValue(vehicleCell, renderDisabledAssignmentDash(names, "data-vehicle-dash"));
};

const syncFuelVehicleCells = (row) => {
  if (!row) return;
  if (rowFeesAreLocked(row)) return;
  const fuelCell = row.querySelector("[data-fuel-cell]");
  const vehicleCell = row.querySelector("[data-vehicle-cell]");
  if (!fuelCell || !vehicleCell) return;
  const names = fuelVehicleNames(row);
  const kmInput = row.querySelector("[data-km-input]");
  const kmValue = Number.parseInt(kmInput?.value || "", 10);
  const isAllowed = Boolean(kmInput) && Number.isInteger(kmValue) && kmValue >= 60 && selectedRowTeamMemberHasCar(row);
  const hasInputs = Boolean(fuelCell.querySelector("[data-fuel-input]") || vehicleCell.querySelector("[data-vehicle-input]"));

  if (!isAllowed && hasInputs) {
    syncAssignmentTotalFee(row);
    return;
  }

  if (!isAllowed) {
    replaceStaffCardFieldValue(fuelCell, renderDisabledAssignmentDash(names, "data-fuel-dash"));
    replaceStaffCardFieldValue(vehicleCell, renderDisabledAssignmentDash(names, "data-vehicle-dash"));
    syncFuel(row, { forceEmpty: true });
    syncVehicleDep(row, { forceEmpty: true });
    syncAssignmentTotalFee(row);
    return;
  }

  if (hasInputs) {
    syncFuel(row, { forceEmpty: true });
    syncVehicleDep(row, { forceEmpty: true });
    return;
  }
  replaceStaffCardFieldValue(fuelCell, renderFuelVehicleCheckbox(names));
  replaceStaffCardFieldValue(vehicleCell, renderDisabledAssignmentDash(names, "data-vehicle-dash"));
  syncAssignmentTotalFee(row);
};

document.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-enable-fuel-vehicle]");
  if (!checkbox || !checkbox.checked) return;
  const row = staffAssignmentRow(checkbox);
  if (rowFeesAreLocked(row)) {
    checkbox.checked = false;
    return;
  }
  enableFuelVehicleInputs(row);
  syncFuel(row, { forceEmpty: true });
  syncVehicleDep(row, { forceEmpty: true });
  syncAssignmentTotalFee(row);
});

document.querySelectorAll("[data-activate-monthly-cell]").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.closest("[data-monthly-session-row]")?.classList.contains("is-monthly-closed")) return;
    const cell = button.closest("[data-monthly-registration-cell]");
    const form = cell?.querySelector(".monthly-registration-form");
    if (!cell || !form) return;
    button.hidden = true;
    form.hidden = false;
    cell.classList.add("is-active");
    form.querySelector("input")?.focus();
  });
});

const initIntegerInputs = (root = document) => {
  root.querySelectorAll("[data-integer-input]").forEach((input) => {
    if (input.dataset.integerInitialized === "true") return;
    input.dataset.integerInitialized = "true";
    input.addEventListener("input", () => {
      if (input.readOnly) return;
      input.value = input.value.replace(/[^0-9]/g, "");
      if (input.matches("[data-total-candidates-input]")) {
        syncCandidateTotalTrends(input.closest("tr"));
      }
      const monthlyForm = input.closest(".monthly-registration-form");
      if (monthlyForm) queueMonthlyRegistrationSave(monthlyForm);
    });
    input.addEventListener("keydown", (event) => {
      if (["-", "+", ".", ",", "e", "E"].includes(event.key)) event.preventDefault();
    });
  });
};

initIntegerInputs();

const syncCandidateTotalTrends = (row) => {
  if (!row) return;
  let previousValue = null;
  row.querySelectorAll("[data-total-candidates-input]").forEach((input) => {
    input.classList.remove("trend-neutral", "trend-increase", "trend-decrease");
    input.removeAttribute("title");
    if (input.value.trim() === "") return;
    const currentValue = Number.parseInt(input.value, 10);
    if (Number.isNaN(currentValue)) return;
    if (previousValue === null) {
      input.classList.add("trend-neutral");
      input.title = "First recorded month";
    } else if (currentValue > previousValue) {
      input.classList.add("trend-increase");
      input.title = `Increase of ${currentValue - previousValue} candidates compared to previous recorded month`;
    } else if (currentValue < previousValue) {
      input.classList.add("trend-decrease");
      input.title = `Decrease of ${previousValue - currentValue} candidates compared to previous recorded month`;
    } else {
      input.classList.add("trend-neutral");
      input.title = "No change compared to previous recorded month";
    }
    previousValue = currentValue;
  });
};

document.querySelectorAll(".monthly-registration-table tbody tr").forEach(syncCandidateTotalTrends);

const monthlyFormIsEmpty = (form) => {
  return Array.from(form.querySelectorAll("[data-integer-input]")).every((input) => input.value.trim() === "");
};

const setMonthlyCellInactive = (form) => {
  const cell = form.closest("[data-monthly-registration-cell]");
  const inactiveButton = cell?.querySelector("[data-activate-monthly-cell]");
  if (!cell || !inactiveButton) return;
  form.hidden = true;
  inactiveButton.hidden = false;
  cell.classList.remove("is-active");
};

const saveMonthlyRegistrationForm = async (form) => {
  if (!form) return;
  form.classList.add("is-saving");
  form.classList.remove("is-error");
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    if (!response.ok) throw new Error("Unable to save monthly registrations.");
    const data = await response.json();
    if (data.monthly_totals) {
      Object.entries(data.monthly_totals).forEach(([month, total]) => {
        const totalElement = document.querySelector(`[data-monthly-total-value="${month}"]`);
        if (!totalElement) return;
        totalElement.classList.remove("trend-neutral", "trend-increase", "trend-decrease", "trend-inactive");
        totalElement.classList.add(`trend-${total.trend || "inactive"}`);
        totalElement.textContent = total.has_data ? total.value : "Inactive";
        totalElement.title = total.tooltip || "";
      });
    }
    if (data.monthly_status) {
      const row = form.closest("[data-monthly-session-row]");
      const statusElement = row?.querySelector("[data-monthly-session-status]");
      if (statusElement) {
        Array.from(statusElement.classList).forEach((className) => {
          if (className.startsWith("exam-status-")) statusElement.classList.remove(className);
        });
        const statusClass = String(data.monthly_status).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
        statusElement.classList.add(`exam-status-${statusClass}`);
        statusElement.textContent = data.monthly_status;
      }
    }
    form.classList.remove("is-saving");
    if (monthlyFormIsEmpty(form)) setMonthlyCellInactive(form);
  } catch (error) {
    form.classList.remove("is-saving");
    form.classList.add("is-error");
  }
};

const queueMonthlyRegistrationSave = (form) => {
  if (form?.closest("[data-monthly-session-row]")?.classList.contains("is-monthly-closed")) return;
  window.clearTimeout(Number(form.dataset.saveTimer || 0));
  const timer = window.setTimeout(() => saveMonthlyRegistrationForm(form), 450);
  form.dataset.saveTimer = String(timer);
};

const sessionMembersFormForElement = (element) => (
  element?.closest?.("[data-session-members-form]")
  || element?.closest?.("[data-session-modal-panel]")?.querySelector("[data-session-members-form]")
  || null
);

const sessionMembersScopeForForm = (form) => form?.closest?.("[data-session-modal-panel]") || form || null;

const syncSessionNonAvailableFields = (form) => {
  if (!form) return;
  const scope = sessionMembersScopeForForm(form);
  const selectedValues = Array.from(scope?.querySelectorAll("[data-session-non-available-picker] input[type='checkbox']:checked") || [])
    .map((checkbox) => checkbox.value)
    .filter(Boolean);
  form.querySelectorAll("[data-row-non-available-fields]").forEach((container) => {
    const sectionKey = container.dataset.nonAvailableSectionKey || "";
    const rowKey = container.dataset.nonAvailableRowKey || "";
    const fieldName = sectionKey && rowKey ? `${sectionKey}_non_available_member_ids_${rowKey}` : "";
    container.innerHTML = "";
    if (!fieldName) return;
    const emptyInput = document.createElement("input");
    emptyInput.type = "hidden";
    emptyInput.name = fieldName;
    emptyInput.value = "";
    container.appendChild(emptyInput);
    selectedValues.forEach((value) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = fieldName;
      input.value = value;
      container.appendChild(input);
    });
  });
};

const syncMemberMultiselect = (picker) => {
  const tags = picker.querySelector("[data-member-tags]");
  const placeholder = picker.querySelector("[data-member-placeholder]");
  if (!tags) return;
  tags.innerHTML = "";
  const checkedMembers = Array.from(picker.querySelectorAll("input[type='checkbox']:checked"));
  checkedMembers.forEach((checkbox) => {
    const tag = document.createElement("span");
    tag.className = "session-member-chip";
    tag.textContent = checkbox.dataset.memberName || checkbox.value;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${checkbox.dataset.memberName || "member"}`);
    remove.textContent = "×";
    remove.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      checkbox.checked = false;
      syncMemberMultiselect(picker);
      const form = sessionMembersFormForElement(picker);
      syncSessionNonAvailableFields(form);
      syncSupervisorMemberAvailability(form);
      markStaffChangesUnsaved(form);
    });

    tag.appendChild(remove);
    tags.appendChild(tag);
  });
  if (placeholder) {
    placeholder.hidden = checkedMembers.length > 0;
  }
};

const normalizeStaffPickerSearch = (value) => String(value || "")
  .normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "")
  .toLowerCase()
  .trim();

const staffPickerOptionText = (option) => normalizeStaffPickerSearch([
  option.dataset.name,
  option.dataset.title,
  option.dataset.baseLabel,
  option.textContent,
].filter(Boolean).join(" "));

const filterStaffPickerOptions = (input, optionsSelector, emptySelector) => {
  const panel = input.closest(".session-member-picker-panel, .team-member-picker-panel");
  if (!panel) return;
  const query = normalizeStaffPickerSearch(input.value);
  let visibleCount = 0;
  panel.querySelectorAll(optionsSelector).forEach((option) => {
    const isBlankOption = option.matches("[data-team-member-option]") && !(option.dataset.value || "");
    const matches = !query || isBlankOption || staffPickerOptionText(option).includes(query);
    option.hidden = !matches;
    if (matches && !isBlankOption) visibleCount += 1;
  });
  const empty = panel.querySelector(emptySelector);
  if (empty) empty.hidden = visibleCount > 0 || !query;
};

const initStaffPickerSearch = (picker, inputSelector, optionsSelector, emptySelector, positionPanel) => {
  const input = picker?.querySelector(inputSelector);
  if (!input || input.dataset.initialized === "true") return;
  input.dataset.initialized = "true";
  const applyFilter = () => {
    filterStaffPickerOptions(input, optionsSelector, emptySelector);
    positionPanel?.(picker);
  };
  input.addEventListener("input", (event) => {
    event.stopPropagation();
    applyFilter();
  });
  input.addEventListener("change", (event) => event.stopPropagation());
  input.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Enter") event.preventDefault();
    if (event.key === "Escape") {
      input.value = "";
      applyFilter();
      picker.open = false;
    }
  });
};

const resetStaffPickerSearch = (picker, inputSelector, optionsSelector, emptySelector) => {
  const input = picker?.querySelector(inputSelector);
  if (!input) return;
  input.value = "";
  filterStaffPickerOptions(input, optionsSelector, emptySelector);
};

const positionMemberMultiselectPanel = (picker) => {
  const panel = picker.querySelector(".session-member-picker-panel");
  const summary = picker.querySelector("summary");
  if (!panel || !summary || !picker.open) return;
  const rect = summary.getBoundingClientRect();
  const viewportGap = 12;
  const preferredWidth = picker.matches("[data-session-non-available-picker]") ? 760 : 620;
  const panelWidth = Math.min(Math.max(rect.width, preferredWidth), window.innerWidth - viewportGap * 2);
  const left = Math.min(Math.max(rect.left, viewportGap), window.innerWidth - panelWidth - viewportGap);
  const availableBelow = window.innerHeight - rect.bottom - viewportGap;
  const availableAbove = rect.top - viewportGap;
  const openAbove = availableAbove >= 160 || availableAbove > availableBelow;
  const maxHeight = Math.max(160, Math.min(260, openAbove ? availableAbove - 6 : availableBelow - 6));
  panel.style.width = `${panelWidth}px`;
  panel.style.maxHeight = `${maxHeight}px`;
  panel.style.left = `${left}px`;
  const panelHeight = Math.min(panel.scrollHeight || maxHeight, maxHeight);
  panel.style.top = openAbove
    ? `${Math.max(viewportGap, rect.top - panelHeight - 6)}px`
    : `${Math.min(window.innerHeight - viewportGap, rect.bottom + 6)}px`;
};

const closeOtherMemberMultiselects = (activePicker) => {
  document.querySelectorAll("[data-member-multiselect][open]").forEach((picker) => {
    if (picker !== activePicker) picker.open = false;
  });
};

const syncPotentialSessionMultiselect = (picker) => {
  const tags = picker.querySelector("[data-potential-session-tags]");
  const placeholder = picker.querySelector("[data-potential-session-placeholder]");
  if (!tags) return;
  tags.innerHTML = "";
  const checkedSessions = Array.from(picker.querySelectorAll("input[type='checkbox']:checked"));
  checkedSessions.forEach((checkbox) => {
    const fullLabel = checkbox.dataset.sessionUnavailable === "true"
      ? "Session no longer available"
      : checkbox.dataset.sessionLabel || checkbox.value;
    const label = checkbox.dataset.sessionUnavailable === "true"
      ? "Session no longer available"
      : checkbox.dataset.sessionChipLabel || fullLabel;
    const tag = document.createElement("span");
    tag.className = "potential-session-chip";
    if (checkbox.dataset.sessionUnavailable === "true") tag.classList.add("is-unavailable");
    tag.textContent = label;
    tag.title = fullLabel;

    if (!checkbox.disabled) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove ${fullLabel}`);
      remove.textContent = "×";
      remove.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        checkbox.checked = false;
        syncPotentialSessionMultiselect(picker);
        positionPotentialSessionMultiselectPanel(picker);
      });
      tag.appendChild(remove);
    }

    tags.appendChild(tag);
  });
  if (placeholder) {
    placeholder.hidden = checkedSessions.length > 0;
  }
};

const positionPotentialSessionMultiselectPanel = (picker) => {
  const panel = picker.querySelector(".potential-session-picker-panel");
  const summary = picker.querySelector("summary");
  if (!panel || !summary || !picker.open) return;
  const rect = summary.getBoundingClientRect();
  const viewportGap = 12;
  const panelWidth = Math.min(rect.width, window.innerWidth - viewportGap * 2);
  const left = Math.min(Math.max(rect.left, viewportGap), window.innerWidth - panelWidth - viewportGap);
  const availableBelow = window.innerHeight - rect.bottom - viewportGap;
  const availableAbove = rect.top - viewportGap;
  const openAbove = availableBelow < 160 && availableAbove > availableBelow;
  const maxHeight = Math.max(160, Math.min(280, openAbove ? availableAbove - 6 : availableBelow - 6));
  panel.style.width = `${panelWidth}px`;
  panel.style.maxHeight = `${maxHeight}px`;
  panel.style.left = `${left}px`;
  const panelHeight = Math.min(panel.scrollHeight || maxHeight, maxHeight);
  panel.style.top = openAbove
    ? `${Math.max(viewportGap, rect.top - panelHeight - 6)}px`
    : `${Math.min(window.innerHeight - viewportGap, rect.bottom + 6)}px`;
};

const closeOtherPotentialSessionMultiselects = (activePicker) => {
  document.querySelectorAll("[data-potential-session-multiselect][open]").forEach((picker) => {
    if (picker !== activePicker) picker.open = false;
  });
};

const closeOtherNoteRecipientPickers = (activePicker) => {
  document.querySelectorAll("[data-note-recipient-picker].is-open").forEach((picker) => {
    if (picker !== activePicker) picker.classList.remove("is-open");
  });
};

const syncNoteRecipientSelect = (select) => {
  const picker = select._noteRecipientPicker;
  const chips = select.parentElement?.querySelector("[data-note-recipient-chips]");
  if (!picker) return;
  const selectedOptions = Array.from(select.selectedOptions).filter((option) => option.value);
  const button = picker.querySelector("[data-note-recipient-toggle]");
  const selectedText = picker.querySelector("[data-note-recipient-selected]");
  const checkboxes = picker.querySelectorAll("input[type='checkbox']");
  checkboxes.forEach((checkbox) => {
    const option = Array.from(select.options).find((item) => item.value === checkbox.value);
    checkbox.checked = Boolean(option?.selected);
  });
  if (selectedText) {
    selectedText.textContent = selectedOptions.length
      ? `${selectedOptions.length} selected`
      : "Select recipients";
  }
  button?.classList.toggle("has-selection", selectedOptions.length > 0);
  if (!chips) return;
  chips.innerHTML = "";
  selectedOptions.forEach((option) => {
    const chip = document.createElement("span");
    chip.className = "note-recipient-selected-chip";
    chip.title = option.textContent.trim();
    chip.textContent = option.textContent.trim();

    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${option.textContent.trim()}`);
    remove.textContent = "×";
    remove.addEventListener("click", (event) => {
      event.preventDefault();
      option.selected = false;
      syncNoteRecipientSelect(select);
    });
    chip.appendChild(remove);
    chips.appendChild(chip);
  });
};

const initNoteRecipientSelects = (root = document) => {
  root.querySelectorAll("[data-note-recipient-select]").forEach((select) => {
    if (select.dataset.initialized === "true") return;
    select.dataset.initialized = "true";
    select.hidden = true;

    const picker = document.createElement("div");
    picker.className = "note-recipient-picker";
    picker.dataset.noteRecipientPicker = "true";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "note-recipient-picker-toggle";
    toggle.dataset.noteRecipientToggle = "true";
    toggle.setAttribute("aria-haspopup", "listbox");
    toggle.innerHTML = '<span data-note-recipient-selected>Select recipients</span><span aria-hidden="true">⌄</span>';

    const panel = document.createElement("div");
    panel.className = "note-recipient-picker-panel";
    panel.setAttribute("role", "listbox");
    panel.setAttribute("aria-multiselectable", "true");

    const options = Array.from(select.options).filter((option) => option.value);
    if (options.length) {
      options.forEach((option) => {
        const row = document.createElement("label");
        row.className = "note-recipient-picker-option";
        row.setAttribute("role", "option");

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = option.value;
        checkbox.checked = option.selected;

        const text = document.createElement("span");
        text.textContent = option.textContent.trim();

        checkbox.addEventListener("change", () => {
          option.selected = checkbox.checked;
          syncNoteRecipientSelect(select);
        });

        row.appendChild(checkbox);
        row.appendChild(text);
        panel.appendChild(row);
      });
    } else {
      const empty = document.createElement("span");
      empty.className = "note-recipient-picker-empty";
      empty.textContent = "No users available";
      panel.appendChild(empty);
    }

    toggle.addEventListener("click", (event) => {
      event.preventDefault();
      const willOpen = !picker.classList.contains("is-open");
      closeOtherNoteRecipientPickers(picker);
      picker.classList.toggle("is-open", willOpen);
    });

    picker.appendChild(toggle);
    picker.appendChild(panel);
    select.insertAdjacentElement("beforebegin", picker);
    select._noteRecipientPicker = picker;
    syncNoteRecipientSelect(select);
  });
};

const positionTeamMemberPickerPanel = (picker) => {
  const panel = picker.querySelector(".team-member-picker-panel");
  const summary = picker.querySelector("summary");
  if (!panel || !summary || !picker.open) return;
  const rect = summary.getBoundingClientRect();
  const viewportGap = 12;
  const panelWidth = Math.min(Math.max(rect.width, 760), window.innerWidth - viewportGap * 2);
  const left = Math.min(Math.max(rect.left, viewportGap), window.innerWidth - panelWidth - viewportGap);
  const availableBelow = window.innerHeight - rect.bottom - viewportGap;
  const availableAbove = rect.top - viewportGap;
  const openAbove = availableAbove >= 180 || availableAbove > availableBelow;
  const maxHeight = Math.max(180, Math.min(320, openAbove ? availableAbove - 6 : availableBelow - 6));
  panel.style.width = `${panelWidth}px`;
  panel.style.maxHeight = `${maxHeight}px`;
  panel.style.left = `${left}px`;
  const panelHeight = Math.min(panel.scrollHeight || maxHeight, maxHeight);
  panel.style.top = openAbove
    ? `${Math.max(viewportGap, rect.top - panelHeight - 6)}px`
    : `${Math.min(window.innerHeight - viewportGap, rect.bottom + 6)}px`;
};

const selectedSupervisorMemberValues = (form, excludedControl) => {
  const selected = [];
  if (!form) return selected;
  const scope = sessionMembersScopeForForm(form);
  scope.querySelectorAll("[data-member-multiselect] input[type='checkbox']:checked").forEach((checkbox) => {
    if (checkbox !== excludedControl) selected.push(checkbox.value);
  });
  scope.querySelectorAll("[data-team-member-select]").forEach((select) => {
    if (select !== excludedControl && select.value) selected.push(select.value);
  });
  scope.querySelectorAll("[data-emergency-contact-select]").forEach((select) => {
    if (select !== excludedControl && select.value) selected.push(select.value);
  });
  return selected;
};

const selectedTeamMemberOption = (input) => {
  const row = input.closest(".staff-member-select-row");
  return Array.from(row?.querySelectorAll("[data-team-member-option]") || [])
    .find((option) => option.dataset.value === (input.value || "")) || null;
};

const staffAssignmentRow = (element) => element?.closest?.("[data-supervisor-row]") || null;
const EXAM_SESSION_PLANNER_PARTICIPATION_STATUSES = new Set(["Pending", "Pre-confirmation sent", "Pre-confirmed"]);
const selectedAssignmentIsPotentialEntry = (row) => {
  const input = row?.querySelector("[data-team-member-select]");
  const option = input ? selectedTeamMemberOption(input) : null;
  return option?.dataset.entryType === "potential";
};

const syncPotentialEntryParticipationOptions = (row) => {
  const select = row?.querySelector("[data-participation-select]");
  if (!select) return;
  const isPotentialEntry = selectedAssignmentIsPotentialEntry(row);
  Array.from(select.options).forEach((option) => {
    if (option.dataset.externalParticipationStatus === "true") {
      option.disabled = true;
      option.hidden = select.value !== option.value;
      return;
    }
    const blocked = isPotentialEntry && !EXAM_SESSION_PLANNER_PARTICIPATION_STATUSES.has(option.value);
    option.disabled = blocked;
    option.hidden = blocked;
  });
  if (isPotentialEntry && !EXAM_SESSION_PLANNER_PARTICIPATION_STATUSES.has(select.value)) {
    select.value = "Pending";
  }
};

const resetParticipationWithoutTeamMember = (row) => {
  const teamMemberSelect = row?.querySelector("[data-team-member-select]");
  const participationSelect = row?.querySelector("[data-participation-select]");
  if (!teamMemberSelect || !participationSelect) return false;
  const hasTeamMember = Boolean(teamMemberSelect.value);
  Array.from(participationSelect.options).forEach((option) => {
    if (option.dataset.externalParticipationStatus === "true") {
      option.disabled = true;
      option.hidden = participationSelect.value !== option.value;
      return;
    }
    option.disabled = !hasTeamMember && option.value !== "Pending";
    option.hidden = false;
  });
  if (hasTeamMember) return false;
  if (participationSelect.value !== "Pending") {
    participationSelect.value = "Pending";
  }
  if (typeof syncParticipationSelect === "function") {
    syncParticipationSelect(participationSelect);
  }
  return true;
};

const syncSameDateAssignmentConflictAlerts = () => {
  if (document.querySelector(".session-fullscreen-modal")) return;
  const panels = Array.from(document.querySelectorAll("[data-session-modal-panel]"));
  const messagesBySession = new Map(panels.map((panel) => [panel.dataset.sessionId || "", []]));
  const groupedAssignments = new Map();

  panels.forEach((panel) => {
    const sessionId = panel.dataset.sessionId || "";
    const sessionName = panel.dataset.sessionName || "";
    const sessionDate = panel.dataset.sessionDate || "";
    const sessionDateLabel = panel.dataset.sessionDateLabel || "";
    panel.querySelectorAll("[data-team-member-select]").forEach((input) => {
      if (!input.value || !sessionDate) return;
      const option = selectedTeamMemberOption(input);
      const memberName = option?.dataset.name || "Staff member";
      const groupKey = `${input.value}|${sessionDate}`;
      if (!groupedAssignments.has(groupKey)) {
        groupedAssignments.set(groupKey, {
          memberName,
          sessionDateLabel,
          sessions: new Map(),
        });
      }
      groupedAssignments.get(groupKey).sessions.set(sessionId, sessionName);
    });
  });

  groupedAssignments.forEach((group) => {
    if (group.sessions.size < 2) return;
    group.sessions.forEach((sessionName, sessionId) => {
      const otherSessionNames = Array.from(group.sessions.entries())
        .filter(([otherSessionId]) => otherSessionId !== sessionId)
        .map(([, otherSessionName]) => otherSessionName);
      const sessionWord = otherSessionNames.length === 1 ? "session" : "sessions";
      messagesBySession.get(sessionId)?.push(
        `${group.memberName} is also assigned on ${group.sessionDateLabel} in ${sessionWord}: ${otherSessionNames.join(", ")}.`
      );
    });
  });

  panels.forEach((panel) => {
    const alert = panel.querySelector("[data-same-date-conflict-alert]");
    const messagesWrap = panel.querySelector("[data-same-date-conflict-messages]");
    const messages = messagesBySession.get(panel.dataset.sessionId || "") || [];
    if (!alert || !messagesWrap) return;
    messagesWrap.replaceChildren(...messages.map((message) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = message;
      return paragraph;
    }));
    alert.hidden = messages.length === 0;
  });
};

const countTeamMemberValues = (attributeName) => {
  const counts = {};
  document.querySelectorAll("[data-team-member-select]").forEach((input) => {
    const value = attributeName ? input.dataset[attributeName] : input.value;
    if (!value) return;
    counts[value] = (counts[value] || 0) + 1;
  });
  return counts;
};

const refreshTeamMemberSessionCounts = () => {
  const originalCounts = countTeamMemberValues("originalValue");
  const currentCounts = countTeamMemberValues();

  document.querySelectorAll("[data-team-member-option][data-value]").forEach((option) => {
    if (!option.dataset.value) return;
    const baseCount = Number.parseInt(option.dataset.baseSessionCount || option.dataset.sessionCount || "0", 10) || 0;
    const currentCount = currentCounts[option.dataset.value] || 0;
    const originalCount = originalCounts[option.dataset.value] || 0;
    const sessionCount = Math.max(0, baseCount + currentCount - originalCount);
    option.dataset.sessionCount = String(sessionCount);
    const countLabel = option.querySelector(".staff-option-count");
    if (countLabel) countLabel.textContent = `(${sessionCount})`;
  });

  document.querySelectorAll("[data-team-member-select]").forEach(syncTeamMemberSelect);
};

const syncSupervisorMemberAvailability = (form) => {
  if (!form) return;
  const scope = sessionMembersScopeForForm(form);
  scope?.querySelectorAll("[data-member-multiselect] input[type='checkbox']").forEach((checkbox) => {
    const usedElsewhere = selectedSupervisorMemberValues(form, checkbox).includes(checkbox.value);
    const label = checkbox.closest(".session-member-option");
    checkbox.disabled = !checkbox.checked && usedElsewhere;
    label?.classList.toggle("is-unavailable", checkbox.disabled);
  });

  scope?.querySelectorAll("[data-team-member-select]").forEach((input) => {
    const picker = input.closest(".staff-member-select-row")?.querySelector("[data-team-member-picker]");
    picker?.querySelectorAll("[data-team-member-option]").forEach((option) => {
      if (!option.dataset.value) return;
      const usedElsewhere = selectedSupervisorMemberValues(form, input).includes(option.dataset.value);
      option.disabled = option.dataset.value !== input.value && usedElsewhere;
      option.classList.toggle("is-unavailable", option.disabled);
    });
    syncTeamMemberSelect(input);
  });

  scope?.querySelectorAll("[data-emergency-contact-select]").forEach((select) => {
    const usedValues = selectedSupervisorMemberValues(form, select);
    Array.from(select.options).forEach((option) => {
      if (!option.value) return;
      const usedElsewhere = usedValues.includes(option.value);
      option.disabled = option.value !== select.value && usedElsewhere;
      option.hidden = option.disabled;
    });
  });
};

const initMemberMultiselects = (root = document) => {
  root.querySelectorAll("[data-member-multiselect]").forEach((picker) => {
    if (picker.dataset.initialized === "true") return;
    picker.dataset.initialized = "true";
    initStaffPickerSearch(
      picker,
      "[data-member-search]",
      ".session-member-option",
      "[data-member-search-empty]",
      positionMemberMultiselectPanel
    );
    picker.addEventListener("toggle", () => {
      if (picker.open) {
        closeOtherMemberMultiselects(picker);
        resetStaffPickerSearch(picker, "[data-member-search]", ".session-member-option", "[data-member-search-empty]");
        positionMemberMultiselectPanel(picker);
        window.requestAnimationFrame(() => picker.querySelector("[data-member-search]")?.focus({ preventScroll: true }));
      }
    });
    picker.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const form = sessionMembersFormForElement(picker);
        syncMemberMultiselect(picker);
        syncSessionNonAvailableFields(form);
        syncSupervisorMemberAvailability(form);
        markStaffChangesUnsaved(form);
        positionMemberMultiselectPanel(picker);
      });
    });
    syncMemberMultiselect(picker);
    syncSessionNonAvailableFields(sessionMembersFormForElement(picker));
  });
};

const syncEmergencyContactControl = (control) => {
  const requiredCheckbox = control?.querySelector("[data-emergency-contact-required]");
  const notRequiredCheckbox = control?.querySelector("[data-emergency-contact-not-required]");
  const selectWrap = control?.querySelector("[data-emergency-contact-select-wrap]");
  if (!requiredCheckbox || !notRequiredCheckbox || !selectWrap) return;
  const required = requiredCheckbox.checked && !notRequiredCheckbox.checked;
  selectWrap.hidden = !required;
  const participationClasses = [
    "participation-pending",
    "participation-pre-confirmation-sent",
    "participation-pre-confirmed",
    "participation-official-confirmation-sent",
    "participation-confirmed",
    "participation-sent",
    "participation-assigned",
    "participation-declined",
    "participation-cancelled",
  ];
  selectWrap.querySelectorAll("[data-emergency-contact-row]").forEach((row) => {
    const isFirstRow = row === selectWrap.querySelector("[data-emergency-contact-row]");
    row.querySelectorAll(".modal-emergency-contact-row-title").forEach((title) => {
      title.hidden = !isFirstRow;
    });
    const select = row.querySelector("[data-emergency-contact-select]");
    const roleToCover = row.querySelector("[data-emergency-contact-role-to-cover]");
    const statusSelect = row.querySelector("[data-emergency-contact-status-select]");
    const declinedButton = row.querySelector("[data-emergency-contact-declined-button]");
    const timeField = row.querySelector("[data-emergency-contact-time-field]");
    const timeInputs = Array.from(row.querySelectorAll("[data-emergency-contact-time-input]") || []);
    if (!select) return;
    select.disabled = !required;
    if (!required) select.value = "";
    const hasMember = Boolean(select.value);
    const preserveTimeWithoutMember = row.dataset.emergencyContactPreserveTime === "true";
    if (hasMember) delete row.dataset.emergencyContactPreserveTime;
    if (roleToCover) roleToCover.hidden = !required || hasMember;
    if (statusSelect) {
      const savedMemberId = row.dataset.emergencyContactSavedMemberId || "";
      const savedStatus = row.dataset.emergencyContactSavedStatus || "Pending";
      statusSelect.disabled = !required;
      if (!required) statusSelect.value = "Pending";
      if (select.value && statusSelect.dataset.currentMemberId !== select.value) {
        statusSelect.value = select.value === savedMemberId ? savedStatus : "Pending";
        statusSelect.dataset.currentMemberId = select.value;
      }
      Array.from(statusSelect.options).forEach((option) => {
        if (option.dataset.externalParticipationStatus === "true") {
          option.disabled = true;
          option.hidden = statusSelect.value !== option.value;
        }
      });
      statusSelect.classList.remove(...participationClasses);
      statusSelect.classList.add(`participation-${(statusSelect.value || "Pending").toLowerCase().replace(/\s+/g, "-")}`);
      statusSelect.hidden = !required || !hasMember;
    }
    if (declinedButton) {
      declinedButton.hidden = !required || !hasMember;
      declinedButton.disabled = !required || !hasMember;
    }
    if (timeField) timeField.hidden = !required || (!hasMember && !preserveTimeWithoutMember);
    timeInputs.forEach((input) => {
      input.disabled = !required;
      if (!required || (!hasMember && !preserveTimeWithoutMember)) input.value = "";
      syncTimeRangeError(input);
    });
  });
};

const initEmergencyContactControls = (root = document) => {
  root.querySelectorAll("[data-emergency-contact-control]").forEach((control) => {
    if (control.dataset.initialized === "true") return;
    control.dataset.initialized = "true";
    const requiredCheckbox = control.querySelector("[data-emergency-contact-required]");
    const notRequiredCheckbox = control.querySelector("[data-emergency-contact-not-required]");
    requiredCheckbox?.addEventListener("change", () => {
      if (requiredCheckbox.checked && notRequiredCheckbox) notRequiredCheckbox.checked = false;
      syncEmergencyContactControl(control);
      markStaffChangesUnsaved(sessionMembersFormForElement(control));
    });
    notRequiredCheckbox?.addEventListener("change", () => {
      if (notRequiredCheckbox.checked && requiredCheckbox) requiredCheckbox.checked = false;
      syncEmergencyContactControl(control);
      markStaffChangesUnsaved(sessionMembersFormForElement(control));
    });
    control.addEventListener("change", (event) => {
      if (!event.target.closest("[data-emergency-contact-select], [data-emergency-contact-status-select]")) return;
      syncEmergencyContactControl(control);
      syncSupervisorMemberAvailability(sessionMembersFormForElement(control));
      markStaffChangesUnsaved(sessionMembersFormForElement(control));
    });
    control.addEventListener("input", (event) => {
      if (event.target.closest("[data-emergency-contact-time-input]")) {
        markStaffChangesUnsaved(sessionMembersFormForElement(control));
      }
    });
    control.addEventListener("click", (event) => {
      const addButton = event.target.closest("[data-add-emergency-contact-row]");
      const removeButton = event.target.closest("[data-remove-emergency-contact-row]");
      const declinedButton = event.target.closest("[data-emergency-contact-declined-button]");
      if (declinedButton) {
        event.preventDefault();
        event.stopPropagation();
        const row = declinedButton.closest("[data-emergency-contact-row]");
        const select = row?.querySelector("[data-emergency-contact-select]");
        const selectedValue = select?.value || "";
        if (!row || !selectedValue) return;
        if (!window.confirm("Please confirm this staff member declined their participation.")) return;
        const form = sessionMembersFormForElement(control);
        markStaffMemberNonAvailable(form, selectedValue);
        row.dataset.emergencyContactPreserveTime = "true";
        const preserveInput = row.querySelector("[data-emergency-contact-preserve-time-input]");
        if (preserveInput) preserveInput.value = "1";
        select.value = "";
        const statusSelect = row.querySelector("[data-emergency-contact-status-select]");
        if (statusSelect) {
          statusSelect.value = "Pending";
          statusSelect.dataset.currentMemberId = "";
        }
        syncEmergencyContactControl(control);
        syncSupervisorMemberAvailability(form);
        markStaffChangesUnsaved(form);
        return;
      }
      if (addButton) {
        const row = addButton.closest("[data-emergency-contact-row]");
        const clone = row?.cloneNode(true);
        if (!clone) return;
        clone.dataset.emergencyContactSavedMemberId = "";
        clone.dataset.emergencyContactSavedStatus = "Pending";
        clone.querySelectorAll("select").forEach((select) => {
          select.value = select.matches("[data-emergency-contact-status-select]") ? "Pending" : "";
          select.dataset.currentMemberId = "";
          select.hidden = select.matches("[data-emergency-contact-status-select]");
        });
        clone.querySelectorAll("input").forEach((input) => {
          input.value = "";
          input.dataset.timeInitialized = "";
        });
        const preserveInput = clone.querySelector("[data-emergency-contact-preserve-time-input]");
        if (preserveInput) preserveInput.value = "";
        clone.querySelector("[data-emergency-contact-role-to-cover]")?.removeAttribute("hidden");
        clone.querySelector("[data-emergency-contact-declined-button]")?.setAttribute("hidden", "");
        clone.querySelector("[data-emergency-contact-declined-button]")?.setAttribute("disabled", "");
        clone.querySelectorAll(".modal-emergency-contact-row-title").forEach((title) => {
          title.hidden = true;
        });
        clone.querySelector("[data-emergency-contact-time-field]")?.setAttribute("hidden", "");
        clone.querySelector("[data-remove-emergency-contact-row]")?.removeAttribute("hidden");
        row.after(clone);
        initTimeInputs(clone);
        syncEmergencyContactControl(control);
        syncSupervisorMemberAvailability(sessionMembersFormForElement(control));
        clone.querySelector("[data-emergency-contact-select]")?.focus();
        markStaffChangesUnsaved(sessionMembersFormForElement(control));
      }
      if (removeButton) {
        const row = removeButton.closest("[data-emergency-contact-row]");
        if (row && control.querySelectorAll("[data-emergency-contact-row]").length > 1) {
          row.remove();
          syncEmergencyContactControl(control);
          syncSupervisorMemberAvailability(sessionMembersFormForElement(control));
          markStaffChangesUnsaved(sessionMembersFormForElement(control));
        }
      }
    });
    syncEmergencyContactControl(control);
    syncSupervisorMemberAvailability(sessionMembersFormForElement(control));
  });
};

const initPotentialSessionMultiselects = (root = document) => {
  root.querySelectorAll("[data-potential-session-multiselect]").forEach((picker) => {
    if (picker.dataset.initialized === "true") return;
    picker.dataset.initialized = "true";
    picker.addEventListener("toggle", () => {
      if (picker.open) {
        closeOtherMemberMultiselects();
        closeOtherPotentialSessionMultiselects(picker);
        positionPotentialSessionMultiselectPanel(picker);
      }
    });
    picker.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        syncPotentialSessionMultiselect(picker);
        positionPotentialSessionMultiselectPanel(picker);
      });
    });
    syncPotentialSessionMultiselect(picker);
  });
};

document.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-toggle-preassigned-session-editor]");
  if (!toggle) return;
  event.preventDefault();
  const section = toggle.closest(".potential-preassigned-readonly");
  const editor = section?.querySelector("[data-preassigned-session-editor]");
  if (!editor) return;
  const shouldShow = editor.hidden;
  editor.hidden = !shouldShow;
  toggle.classList.toggle("is-active", shouldShow);
  toggle.setAttribute("aria-expanded", shouldShow ? "true" : "false");
  initPotentialSessionMultiselects(editor);
  if (shouldShow) {
    window.requestAnimationFrame(() => {
      const picker = editor.querySelector("[data-potential-session-multiselect]");
      picker?.querySelector("summary")?.focus();
    });
  }
});

document.addEventListener("click", (event) => {
  document.querySelectorAll("[data-member-multiselect][open]").forEach((picker) => {
    if (!picker.contains(event.target)) picker.open = false;
  });
  document.querySelectorAll("[data-potential-session-multiselect][open]").forEach((picker) => {
    if (!picker.contains(event.target)) picker.open = false;
  });
  document.querySelectorAll("[data-logistics-provider-picker][open]").forEach((picker) => {
    if (!picker.contains(event.target)) picker.open = false;
  });
  document.querySelectorAll("[data-note-recipient-picker].is-open").forEach((picker) => {
    if (!picker.contains(event.target)) picker.classList.remove("is-open");
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll("[data-member-multiselect][open]").forEach((picker) => {
    picker.open = false;
  });
  document.querySelectorAll("[data-potential-session-multiselect][open]").forEach((picker) => {
    picker.open = false;
  });
  document.querySelectorAll("[data-logistics-provider-picker][open]").forEach((picker) => {
    picker.open = false;
  });
  document.querySelectorAll("[data-note-recipient-picker].is-open").forEach((picker) => {
    picker.classList.remove("is-open");
  });
});

window.addEventListener("resize", () => {
  document.querySelectorAll("[data-member-multiselect][open]").forEach(positionMemberMultiselectPanel);
  document.querySelectorAll("[data-potential-session-multiselect][open]").forEach(positionPotentialSessionMultiselectPanel);
  document.querySelectorAll("[data-team-member-picker][open]").forEach(positionTeamMemberPickerPanel);
  document.querySelectorAll("[data-logistics-provider-picker][open]").forEach(positionLogisticsProviderPickerPanel);
});

window.addEventListener("scroll", () => {
  document.querySelectorAll("[data-member-multiselect][open]").forEach(positionMemberMultiselectPanel);
  document.querySelectorAll("[data-potential-session-multiselect][open]").forEach(positionPotentialSessionMultiselectPanel);
  document.querySelectorAll("[data-team-member-picker][open]").forEach(positionTeamMemberPickerPanel);
  document.querySelectorAll("[data-logistics-provider-picker][open]").forEach(positionLogisticsProviderPickerPanel);
}, true);

const syncTeamMemberSelect = (select) => {
  select.classList.remove("is-empty", "is-warning", "is-complete");
  const row = staffAssignmentRow(select);
  const declinedButton = row?.querySelector("[data-staff-declined-button]");
  if (declinedButton) declinedButton.disabled = !select.value;
  const picker = select.closest(".staff-member-select-row")?.querySelector("[data-team-member-picker]");
  const summary = picker?.querySelector("[data-team-member-selected]");
  const option = selectedTeamMemberOption(select);
  picker?.classList.remove("is-empty", "is-warning", "is-complete");
  if (!option || !select.value) {
    select.classList.add("is-empty");
    picker?.classList.add("is-empty");
    if (summary) summary.innerHTML = '<span class="team-member-placeholder" title="Select a staff member to cover this role.">Role to cover</span>';
    const cardTitle = row?.querySelector("[data-staff-card-title]");
    if (cardTitle) cardTitle.textContent = "Role to cover";
    syncStaffMemberAddressButton(select);
    syncStaffMemberEmailCell(select);
    syncFuelVehicleCells(row);
    syncFuel(row, { forceEmpty: true });
    syncVehicleDep(row, { forceEmpty: true });
    syncSeniority(row);
    resetParticipationWithoutTeamMember(row);
    syncLogisticsStaffMemberLists(select.closest("[data-session-members-form]"));
    return;
  }
  const state = option.dataset.state || "warning";
  syncPotentialEntryParticipationOptions(row);
  select.classList.add(state === "completed" ? "is-complete" : "is-warning");
  picker?.classList.add(state === "completed" ? "is-complete" : "is-warning");
  if (summary) {
    const location = option.querySelector(".staff-option-location")?.textContent.trim() || "";
    const seniorBadge = option.dataset.seniority === "true" ? '<span class="staff-option-senior">Senior</span>' : "";
    const carBadge = option.dataset.hasCar === "true" ? '<span class="staff-option-car">Has a car</span>' : "";
    const sessionCount = option.dataset.sessionCount || "0";
    const countBadge = `<span class="staff-option-count">(${sessionCount})</span>`;
    summary.innerHTML = `${state === "completed" ? '<span class="team-member-check">✓</span>' : ""}<span>${option.dataset.name || ""}</span>${location ? `<span class="staff-option-location">${location}</span>` : ""}${seniorBadge}${carBadge}${countBadge}`;
  }
  const cardTitle = row?.querySelector("[data-staff-card-title]");
  if (cardTitle) cardTitle.textContent = option.dataset.name || "Role to cover";
  syncStaffMemberAddressButton(select);
  syncStaffMemberEmailCell(select);
  syncFuelVehicleCells(row);
  syncFuel(row, { forceEmpty: true });
  syncVehicleDep(row, { forceEmpty: true });
  syncSeniority(row);
  resetParticipationWithoutTeamMember(row);
  syncLogisticsStaffMemberLists(select.closest("[data-session-members-form]"));
};

const syncStaffMemberEmailCell = (select) => {
  const row = staffAssignmentRow(select);
  const cell = row?.querySelector("[data-staff-email-cell]");
  if (!cell) return;
  const option = selectedTeamMemberOption(select);
  const email = option?.dataset.email || "";
  if (!select.value) {
    cell.innerHTML = '<span class="muted">-</span>';
    return;
  }
  const wrapper = document.createElement("div");
  wrapper.className = "staff-email-actions";
  if (email) {
    const link = document.createElement("a");
    link.href = "#";
    link.dataset.staffGmailLink = "";
    link.textContent = email;
    syncStaffGmailLink(link);
    wrapper.appendChild(link);
  } else {
    const dash = document.createElement("span");
    dash.className = "muted";
    dash.textContent = "-";
    wrapper.appendChild(dash);
  }
  const chip = document.createElement("button");
  chip.className = "staff-contact-email-chip";
  chip.type = "button";
  chip.dataset.staffPreconfirmationEmail = "";
  chip.textContent = "Pre-confirmation email";
  chip.disabled = document.querySelector("main[data-current-menu-can-edit='false']") !== null;
  wrapper.appendChild(chip);
  cell.replaceChildren(wrapper);
  initStaffGmailLinks(cell);
  initStaffPreconfirmationEmailButtons(cell);
  syncInvitationEmailCopyButtons(row.closest("[data-session-members-form]"));
};

const parseFeeValue = (value) => {
  const normalized = String(value || "").replace(/\./g, "").replace(",", ".").replace(/[^0-9.-]/g, "");
  if (!normalized || normalized === "-" || normalized === ".") return null;
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) ? parsed : null;
};

const formatFeeTotal = (value) => {
  if (!Number.isFinite(value)) return "-";
  return formatMoney(value);
};

const parseRoleFeeBase = (value) => {
  const normalized = String(value || "").replace(/\./g, "").replace(",", ".");
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) ? parsed : null;
};

const currencyForAssignmentCost = (row, input) => {
  const valueCurrency = currencyFromFeeValue(input?.value || "");
  if (valueCurrency) return valueCurrency;
  const currencySelectors = [
    ["data-role-fee-input", "[data-role-fee-currency-input]"],
    ["data-device-dep-input", "[data-device-dep-currency-input]"],
    ["data-commuting-input", "[data-commuting-currency-input]"],
    ["data-fuel-input", "[data-fuel-currency-input]"],
    ["data-vehicle-input", "[data-vehicle-currency-input]"],
    ["data-seniority-input", "[data-seniority-currency-input]"],
  ];
  const match = currencySelectors.find(([attribute]) => input?.hasAttribute(attribute));
  if (!match) return "";
  return row.querySelector(match[1])?.value || "";
};

const formatMoney = (value) => {
  if (!Number.isFinite(value)) return "";
  const sign = value < 0 ? "-" : "";
  const absoluteValue = Math.abs(value);
  const integerPart = Math.floor(absoluteValue);
  const decimalPart = absoluteValue - integerPart;
  const rounded = decimalPart <= 0.5 + Number.EPSILON ? integerPart : integerPart + 1;
  return `${sign}${String(rounded).replace(/\B(?=(\d{3})+(?!\d))/g, ".")}`;
};

const formatDecimalNumber = (value) => {
  if (!Number.isFinite(value)) return "";
  const rounded = Math.round((value + Number.EPSILON) * 100) / 100;
  const [integerPart, decimalPart = ""] = rounded.toFixed(2).split(".");
  const grouped = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decimals = decimalPart.replace(/0+$/, "");
  return decimals ? `${grouped},${decimals}` : grouped;
};

const currencyFromFeeValue = (value) => {
  const match = String(value || "").match(/^\s*([A-Z]{3})\b/);
  return match ? match[1] : "";
};

const timeInputMinutes = (value) => {
  const match = String(value || "").match(/^(\d{2}):(\d{2})$/);
  if (!match) return null;
  const hours = Number.parseInt(match[1], 10);
  const minutes = Number.parseInt(match[2], 10);
  if (hours < 0 || hours > 24 || minutes < 0 || minutes > 59) return null;
  if (hours === 24 && minutes !== 0) return null;
  return hours * 60 + minutes;
};

const rowTimeRangeMinutes = (row) => {
  let total = 0;
  row.querySelectorAll("[data-time-range-row]").forEach((rangeRow) => {
    const inputs = rangeRow.querySelectorAll("[data-time-input]");
    const start = timeInputMinutes(inputs[0]?.value || "");
    const end = timeInputMinutes(inputs[1]?.value || "");
    if (start === null || end === null || end <= start) return;
    total += end - start;
  });
  return total;
};

const rowFeesAreLocked = (row) => {
  const status = row?.querySelector("[data-participation-select]")?.value || "Pending";
  return !EXAM_SESSION_PLANNER_PARTICIPATION_STATUSES.has(status);
};

const rowHasManualFeeOverride = (row) => row?.querySelector("[data-manual-fee-override]")?.value === "1";

const syncEditFeesButton = (row) => {
  if (!row) return;
  const button = row.querySelector("[data-edit-assignment-fees]");
  const status = row.querySelector("[data-participation-select]")?.value || "Pending";
  if (!button) return;
  button.hidden = !EXAM_SESSION_PLANNER_PARTICIPATION_STATUSES.has(status);
  button.textContent = row.classList.contains("is-manual-fee-editing")
    ? "Save"
    : rowHasManualFeeOverride(row)
      ? "Reset"
      : "Edit";
  button.classList.toggle("is-active", rowHasManualFeeOverride(row));
};

const syncCalculatedFieldLocks = (row) => {
  if (!row) return;
  const locked = rowFeesAreLocked(row);
  row.classList.toggle("is-fee-locked", locked);
  row.classList.toggle("is-row-locked", locked);
  syncEditFeesButton(row);
  row.querySelectorAll("[data-km-input], [data-time-input], .assignment-cost-input").forEach((input) => {
    input.readOnly = locked;
    input.classList.toggle("is-locked", locked);
  });
  row.querySelectorAll("button").forEach((button) => {
    if (button.matches("[data-staff-section-toggle]")) {
      button.disabled = false;
      delete button.dataset.rowLockDisabled;
      return;
    }
    if (button.matches("[data-copy-invitation-email]")) {
      const state = invitationEmailButtonState(button);
      button.disabled = !state.enabled;
      button.title = state.title;
      button.setAttribute("aria-label", state.title);
      button.classList.toggle("is-disabled", !state.enabled);
      if (state.enabled) delete button.dataset.rowLockDisabled;
      return;
    }
    if (button.matches("[data-staff-preconfirmation-email], [data-staff-confirmation-email], [data-staff-final-information-email]")) {
      return;
    }
    if (locked) {
      if (!button.disabled) button.dataset.rowLockDisabled = "true";
      button.disabled = true;
    } else if (button.dataset.rowLockDisabled === "true") {
      button.disabled = false;
      delete button.dataset.rowLockDisabled;
    }
  });
};

const syncLiveFeeCalculations = (row, { forceEmpty = true } = {}) => {
  if (!row || rowFeesAreLocked(row)) {
    syncAssignmentTotalFee(row);
    return;
  }
  if (rowHasManualFeeOverride(row)) {
    syncAssignmentTotalFee(row);
    return;
  }
  syncSupervisorRoleFee(row, { forceEmpty });
  syncDeviceDep(row, { forceEmpty });
  syncCommuting(row, { forceEmpty });
  syncFuelVehicleCells(row);
  syncFuel(row, { forceEmpty });
  syncVehicleDep(row, { forceEmpty });
  syncSeniority(row);
  syncAssignmentTotalFee(row);
};

const syncSupervisorRoleFee = (row, { forceEmpty = false } = {}) => {
  if (!row || !["supervisor", "examiner", "intern"].includes(row.dataset.sectionKey || "")) return;
  if (rowFeesAreLocked(row)) return;
  if (rowHasManualFeeOverride(row)) return;
  const section = row.closest(".session-member-section");
  const display = row.querySelector("[data-role-fee-display]");
  const input = row.querySelector("[data-role-fee-input]");
  const currencyInput = row.querySelector("[data-role-fee-currency-input]");
  const baseInput = row.querySelector("[data-role-fee-base-input]");
  const unitInput = row.querySelector("[data-role-fee-unit-input]");
  if (!display || !input) return;
  const label = section?.dataset.roleFeeLabel || row.dataset.sectionKey || "role";
  const configuredMessage = `No ${label} fee configured`;
  const currency = section?.dataset.roleFeeCurrency || "";
  const base = parseRoleFeeBase(section?.dataset.roleFeeValue || "");
  const unit = section?.dataset.roleFeeUnit || "";
  if (!currency || base === null || !["per hour", "per minute"].includes(unit)) {
    if (forceEmpty || !input.value) {
      input.value = "";
      display.textContent = configuredMessage;
      display.title = configuredMessage;
      currencyInput.value = "";
      baseInput.value = "";
      unitInput.value = "";
      syncSeniority(row);
      syncAssignmentTotalFee(row);
    }
    return;
  }
  const minutes = rowTimeRangeMinutes(row);
  if (minutes <= 0) {
    input.value = "";
    display.textContent = "-";
    display.title = "";
    currencyInput.value = "";
    baseInput.value = "";
    unitInput.value = "";
    syncSeniority(row);
    syncAssignmentTotalFee(row);
    return;
  }
  const amount = unit === "per hour" ? (minutes / 60) * base : minutes * base;
  const formatted = `${currency} ${formatMoney(amount)}`;
  const durationLabel = unit === "per hour" ? `${formatDecimalNumber(minutes / 60)} hours` : `${minutes} minutes`;
  input.value = formatted;
  currencyInput.value = currency;
  baseInput.value = section.dataset.roleFeeValue || "";
  unitInput.value = unit;
  display.textContent = formatted;
  display.title = `Calculation: ${durationLabel} × ${currency} ${section.dataset.roleFeeValue || ""} = ${formatted}`;
  syncSeniority(row);
  syncAssignmentTotalFee(row);
};

const syncSupervisorRoleFeePlaceholder = (row) => {
  if (!row || !["supervisor", "examiner", "intern"].includes(row.dataset.sectionKey || "")) return;
  const input = row.querySelector("[data-role-fee-input]");
  const display = row.querySelector("[data-role-fee-display]");
  if (!input || !display || input.value) return;
  const section = row.closest(".session-member-section");
  const label = section?.dataset.roleFeeLabel || row.dataset.sectionKey || "role";
  const configuredMessage = `No ${label} fee configured`;
  const hasFee = Boolean(
    section?.dataset.roleFeeCurrency &&
    section?.dataset.roleFeeValue &&
    ["per hour", "per minute"].includes(section?.dataset.roleFeeUnit || "")
  );
  display.textContent = hasFee ? "-" : configuredMessage;
  display.title = hasFee ? "" : configuredMessage;
};

const syncDeviceDep = (row, { forceEmpty = false } = {}) => {
  if (!row) return;
  if (rowFeesAreLocked(row)) return;
  if (rowHasManualFeeOverride(row)) return;
  const form = row.closest("[data-session-members-form]");
  const display = row.querySelector("[data-device-dep-display]");
  const input = row.querySelector("[data-device-dep-input]");
  const currencyInput = row.querySelector("[data-device-dep-currency-input]");
  const baseInput = row.querySelector("[data-device-dep-base-input]");
  const unitInput = row.querySelector("[data-device-dep-unit-input]");
  if (!form || !display || !input) return;
  const currency = form.dataset.deviceDepFeeCurrency || "";
  const base = parseRoleFeeBase(form.dataset.deviceDepFeeValue || "");
  const unit = form.dataset.deviceDepFeeUnit || "";
  if (!currency || base === null || !["per hour", "per minute"].includes(unit)) {
    if (forceEmpty || !input.value) {
      input.value = "";
      display.textContent = "No Device dep. fee configured";
      display.title = "No Device dep. fee configured";
      currencyInput.value = "";
      baseInput.value = "";
      unitInput.value = "";
      syncAssignmentTotalFee(row);
    }
    return;
  }
  const minutes = rowTimeRangeMinutes(row);
  if (minutes <= 0) {
    input.value = "";
    display.textContent = "-";
    display.title = "";
    currencyInput.value = "";
    baseInput.value = "";
    unitInput.value = "";
    syncAssignmentTotalFee(row);
    return;
  }
  const amount = unit === "per hour" ? (minutes / 60) * base : minutes * base;
  const formatted = `${currency} ${formatMoney(amount)}`;
  const durationLabel = unit === "per hour" ? `${formatDecimalNumber(minutes / 60)} hours` : `${minutes} minutes`;
  input.value = formatted;
  currencyInput.value = currency;
  baseInput.value = form.dataset.deviceDepFeeValue || "";
  unitInput.value = unit;
  display.textContent = formatted;
  display.title = `Calculation: ${durationLabel} × ${currency} ${form.dataset.deviceDepFeeValue || ""} = ${formatted}`;
  syncAssignmentTotalFee(row);
};

const syncDeviceDepPlaceholder = (row) => {
  if (!row) return;
  const input = row.querySelector("[data-device-dep-input]");
  const display = row.querySelector("[data-device-dep-display]");
  if (!input || !display || input.value) return;
  const form = row.closest("[data-session-members-form]");
  const hasFee = Boolean(form?.dataset.deviceDepFeeCurrency && form?.dataset.deviceDepFeeValue && form?.dataset.deviceDepFeeUnit);
  display.textContent = hasFee ? "-" : "No Device dep. fee configured";
  display.title = hasFee ? "" : "No Device dep. fee configured";
};

const syncCommuting = (row, { forceEmpty = false } = {}) => {
  if (!row) return;
  if (rowFeesAreLocked(row)) return;
  if (rowHasManualFeeOverride(row)) return;
  const form = row.closest("[data-session-members-form]");
  const display = row.querySelector("[data-commuting-display]");
  const input = row.querySelector("[data-commuting-input]");
  const currencyInput = row.querySelector("[data-commuting-currency-input]");
  const baseInput = row.querySelector("[data-commuting-base-input]");
  const unitInput = row.querySelector("[data-commuting-unit-input]");
  if (!form || !display || !input) return;
  const clearFields = () => {
    input.value = "";
    if (currencyInput) currencyInput.value = "";
    if (baseInput) baseInput.value = "";
    if (unitInput) unitInput.value = "";
  };
  const currency = form.dataset.commutingFeeCurrency || "";
  const base = parseRoleFeeBase(form.dataset.commutingFeeValue || "");
  const unit = form.dataset.commutingFeeUnit || "";
  const kmInput = row.querySelector("[data-km-input]");
  const kmValue = Number.parseInt(kmInput?.value || "", 10);

  if (!currency || base === null || unit !== "per km") {
    if (forceEmpty || !input.value) {
      clearFields();
      display.textContent = "No Commuting fee configured";
      display.title = "No Commuting fee configured";
      syncAssignmentTotalFee(row);
    }
    return;
  }

  if (!kmInput || !Number.isInteger(kmValue)) {
    clearFields();
    display.textContent = "-";
    display.title = "";
    syncAssignmentTotalFee(row);
    return;
  }

  const amount = kmValue * base;
  const formatted = `${currency} ${formatMoney(amount)}`;
  input.value = formatted;
  if (currencyInput) currencyInput.value = currency;
  if (baseInput) baseInput.value = form.dataset.commutingFeeValue || "";
  if (unitInput) unitInput.value = unit;
  display.textContent = formatted;
  display.title = `Calculation: ${kmValue} km × ${currency} ${form.dataset.commutingFeeValue || ""} = ${formatted}`;
  syncAssignmentTotalFee(row);
};

const syncCommutingPlaceholder = (row) => {
  if (!row) return;
  const input = row.querySelector("[data-commuting-input]");
  const display = row.querySelector("[data-commuting-display]");
  if (!input || !display || input.value) return;
  const form = row.closest("[data-session-members-form]");
  const hasFee = Boolean(form?.dataset.commutingFeeCurrency && form?.dataset.commutingFeeValue && form?.dataset.commutingFeeUnit === "per km");
  display.textContent = hasFee ? "-" : "No Commuting fee configured";
  display.title = hasFee ? "" : "No Commuting fee configured";
};

const syncFuel = (row, { forceEmpty = false } = {}) => {
  if (!row) return;
  if (rowFeesAreLocked(row)) return;
  if (rowHasManualFeeOverride(row)) return;
  const form = row.closest("[data-session-members-form]");
  const display = row.querySelector("[data-fuel-display]");
  const input = row.querySelector("[data-fuel-input]");
  const currencyInput = row.querySelector("[data-fuel-currency-input]");
  const baseInput = row.querySelector("[data-fuel-base-input]");
  const unitInput = row.querySelector("[data-fuel-unit-input]");
  if (!form || !display || !input) return;
  const clearFields = () => {
    input.value = "";
    if (currencyInput) currencyInput.value = "";
    if (baseInput) baseInput.value = "";
    if (unitInput) unitInput.value = "";
  };
  const kmInput = row.querySelector("[data-km-input]");
  const kmValue = Number.parseInt(kmInput?.value || "", 10);
  if (!selectedRowTeamMemberHasCar(row) || !kmInput || !Number.isInteger(kmValue)) {
    clearFields();
    display.textContent = "-";
    display.title = "";
    syncAssignmentTotalFee(row);
    return;
  }

  const currency = form.dataset.fuelFeeCurrency || "";
  const base = parseRoleFeeBase(form.dataset.fuelFeeValue || "");
  const unit = form.dataset.fuelFeeUnit || "";
  if (!currency || base === null || unit !== "per km") {
    if (forceEmpty || !input.value) {
      clearFields();
      display.textContent = "No Fuel fee configured";
      display.title = "No Fuel fee configured";
      syncAssignmentTotalFee(row);
    }
    return;
  }

  const amount = kmValue * base;
  const formatted = `${currency} ${formatMoney(amount)}`;
  input.value = formatted;
  if (currencyInput) currencyInput.value = currency;
  if (baseInput) baseInput.value = form.dataset.fuelFeeValue || "";
  if (unitInput) unitInput.value = unit;
  display.textContent = formatted;
  display.title = `Calculation: ${kmValue} km × ${currency} ${form.dataset.fuelFeeValue || ""} = ${formatted}`;
  syncAssignmentTotalFee(row);
};

const syncFuelPlaceholder = (row) => {
  if (!row) return;
  const input = row.querySelector("[data-fuel-input]");
  const display = row.querySelector("[data-fuel-display]");
  if (!input || !display || input.value) return;
  const form = row.closest("[data-session-members-form]");
  const hasFee = Boolean(form?.dataset.fuelFeeCurrency && form?.dataset.fuelFeeValue && form?.dataset.fuelFeeUnit === "per km");
  display.textContent = hasFee ? "-" : "No Fuel fee configured";
  display.title = hasFee ? "" : "No Fuel fee configured";
};

const syncVehicleDep = (row, { forceEmpty = false } = {}) => {
  if (!row) return;
  if (rowFeesAreLocked(row)) return;
  if (rowHasManualFeeOverride(row)) return;
  const form = row.closest("[data-session-members-form]");
  const display = row.querySelector("[data-vehicle-display]");
  const input = row.querySelector("[data-vehicle-input]");
  const currencyInput = row.querySelector("[data-vehicle-currency-input]");
  const baseInput = row.querySelector("[data-vehicle-base-input]");
  const unitInput = row.querySelector("[data-vehicle-unit-input]");
  if (!form || !display || !input) return;
  const clearFields = () => {
    input.value = "";
    if (currencyInput) currencyInput.value = "";
    if (baseInput) baseInput.value = "";
    if (unitInput) unitInput.value = "";
  };
  const kmInput = row.querySelector("[data-km-input]");
  const kmValue = Number.parseInt(kmInput?.value || "", 10);
  if (!selectedRowTeamMemberHasCar(row) || !kmInput || !Number.isInteger(kmValue)) {
    clearFields();
    display.textContent = "-";
    display.title = "";
    syncAssignmentTotalFee(row);
    return;
  }

  const currency = form.dataset.vehicleDepFeeCurrency || "";
  const base = parseRoleFeeBase(form.dataset.vehicleDepFeeValue || "");
  const unit = form.dataset.vehicleDepFeeUnit || "";
  if (!currency || base === null || unit !== "per km") {
    if (forceEmpty || !input.value) {
      clearFields();
      display.textContent = "No Vehicle dep. fee configured";
      display.title = "No Vehicle dep. fee configured";
      syncAssignmentTotalFee(row);
    }
    return;
  }

  const amount = kmValue * base;
  const formatted = `${currency} ${formatMoney(amount)}`;
  input.value = formatted;
  if (currencyInput) currencyInput.value = currency;
  if (baseInput) baseInput.value = form.dataset.vehicleDepFeeValue || "";
  if (unitInput) unitInput.value = unit;
  display.textContent = formatted;
  display.title = `Calculation: ${kmValue} km × ${currency} ${form.dataset.vehicleDepFeeValue || ""} = ${formatted}`;
  syncAssignmentTotalFee(row);
};

const syncVehicleDepPlaceholder = (row) => {
  if (!row) return;
  const input = row.querySelector("[data-vehicle-input]");
  const display = row.querySelector("[data-vehicle-display]");
  if (!input || !display || input.value) return;
  const form = row.closest("[data-session-members-form]");
  const hasFee = Boolean(form?.dataset.vehicleDepFeeCurrency && form?.dataset.vehicleDepFeeValue && form?.dataset.vehicleDepFeeUnit === "per km");
  display.textContent = hasFee ? "-" : "No Vehicle dep. fee configured";
  display.title = hasFee ? "" : "No Vehicle dep. fee configured";
};

const syncSeniority = (row) => {
  if (!row) return;
  if (rowFeesAreLocked(row)) return;
  if (rowHasManualFeeOverride(row)) return;
  const display = row.querySelector("[data-seniority-display]");
  const input = row.querySelector("[data-seniority-input]");
  const appliedInput = row.querySelector("[data-seniority-applied-input]");
  const percentageInput = row.querySelector("[data-seniority-percentage-input]");
  const currencyInput = row.querySelector("[data-seniority-currency-input]");
  if (!display || !input) return;
  const clearFields = () => {
    input.value = "";
    if (appliedInput) appliedInput.value = "";
    if (percentageInput) percentageInput.value = "";
    if (currencyInput) currencyInput.value = "";
    display.textContent = "-";
    display.title = "";
  };
  const option = selectedTeamMemberOption(row.querySelector("[data-team-member-select]"));
  const roleFeeInput = row.querySelector("[data-role-fee-input]");
  const roleFeeValue = roleFeeInput?.value || "";
  const roleFeeAmount = parseFeeValue(roleFeeValue);
  if (option?.dataset.seniority !== "true" || roleFeeAmount === null) {
    clearFields();
    syncAssignmentTotalFee(row);
    return;
  }
  const currency = currencyFromFeeValue(roleFeeValue) || row.querySelector("[data-role-fee-currency-input]")?.value || "";
  const amount = roleFeeAmount * 0.2;
  const formatted = `${currency ? `${currency} ` : ""}${formatMoney(amount)}`;
  input.value = formatted;
  if (appliedInput) appliedInput.value = "1";
  if (percentageInput) percentageInput.value = "20%";
  if (currencyInput) currencyInput.value = currency;
  display.textContent = formatted;
  display.title = `Calculation: ${roleFeeValue} × 20% = ${formatted}`;
  syncAssignmentTotalFee(row);
};

const syncSeniorityPlaceholder = (row) => {
  if (!row) return;
  const input = row.querySelector("[data-seniority-input]");
  const display = row.querySelector("[data-seniority-display]");
  if (!input || !display || input.value) return;
  display.textContent = "-";
  display.title = "";
};

const syncAssignmentTotalFee = (row) => {
  const cell = row?.querySelector("[data-total-fee-cell]");
  if (!cell) return;
  const totalsByCurrency = new Map();
  let uncategorizedTotal = 0;
  row.querySelectorAll("[data-role-fee-input], [data-device-dep-input], [data-commuting-input], [data-fuel-input], [data-vehicle-input], [data-seniority-input]").forEach((input) => {
    const value = parseFeeValue(input.value);
    if (value === null) return;
    const currency = currencyForAssignmentCost(row, input);
    if (!currency) {
      uncategorizedTotal += value;
      return;
    }
    totalsByCurrency.set(currency, (totalsByCurrency.get(currency) || 0) + value);
  });
  const totals = Array.from(totalsByCurrency.entries()).map(([currency, total]) => `${currency} ${formatFeeTotal(total)}`);
  if (uncategorizedTotal > 0) {
    totals.push(formatFeeTotal(uncategorizedTotal));
  }
  const value = totals.length ? totals.join(" / ") : "-";
  const valueTarget = cell.querySelector("[data-total-fee-value]");
  if (valueTarget) {
    valueTarget.textContent = value;
  } else {
    cell.textContent = value;
  }
};

const copyTextToClipboard = async (value) => {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const input = document.createElement("textarea");
  input.value = value;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.left = "-9999px";
  document.body.appendChild(input);
  input.select();
  document.execCommand("copy");
  input.remove();
};

const copyHtmlSelectionFallback = (html) => {
  const container = document.createElement("div");
  container.contentEditable = "true";
  container.innerHTML = html;
  container.style.position = "fixed";
  container.style.left = "-9999px";
  container.style.top = "0";
  container.style.width = "1px";
  container.style.height = "1px";
  container.style.overflow = "hidden";
  document.body.appendChild(container);
  const range = document.createRange();
  range.selectNodeContents(container);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  const copied = document.execCommand("copy");
  selection.removeAllRanges();
  container.remove();
  return copied;
};

const copyRichTextToClipboard = async ({ html, text }) => {
  if (navigator.clipboard?.write && window.ClipboardItem) {
    try {
      const item = new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([text], { type: "text/plain" }),
      });
      await navigator.clipboard.write([item]);
      return;
    } catch (error) {
      // Some browsers expose ClipboardItem but reject rich writes on localhost.
    }
  }
  if (copyHtmlSelectionFallback(html)) {
    return;
  }
  await copyTextToClipboard(text);
};

const cleanEmailValue = (value) => {
  const text = String(value || "").trim();
  if (!text || ["-", "null", "undefined", "None"].includes(text)) return "";
  return text;
};

const escapeEmailHtml = (value) => cleanEmailValue(value)
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;");

const escapeEmailAttribute = (value) => escapeEmailHtml(value).replace(/'/g, "&#39;");

const emailLinkIsUsable = (value) => /^https?:\/\//i.test(cleanEmailValue(value));

const ordinalSuffix = (day) => {
  const mod100 = day % 100;
  if (mod100 >= 11 && mod100 <= 13) return "th";
  if (day % 10 === 1) return "st";
  if (day % 10 === 2) return "nd";
  if (day % 10 === 3) return "rd";
  return "th";
};

const formatInvitationDate = (isoDate) => {
  const match = cleanEmailValue(isoDate).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return "";
  const year = Number.parseInt(match[1], 10);
  const monthIndex = Number.parseInt(match[2], 10) - 1;
  const day = Number.parseInt(match[3], 10);
  const date = new Date(year, monthIndex, day);
  const weekday = date.toLocaleDateString("en-US", { weekday: "long" });
  const month = date.toLocaleDateString("en-US", { month: "long" });
  return `${weekday}, ${month} ${day}${ordinalSuffix(day)}, ${year}`;
};

const formatInterviewTimeForEmail = (value) => {
  const match = cleanEmailValue(value).match(/^(\d{2}):(\d{2})(?::\d{2})?$/);
  if (!match) return "";
  let hour = Number.parseInt(match[1], 10);
  const minute = Number.parseInt(match[2], 10);
  if (Number.isNaN(hour) || Number.isNaN(minute)) return "";
  const suffix = hour >= 12 ? "pm" : "am";
  hour %= 12;
  if (hour === 0) hour = 12;
  return minute ? `${hour}:${String(minute).padStart(2, "0")}${suffix}` : `${hour}${suffix}`;
};

const formatPotentialInterviewDateTime = (isoDate, timeValue) => {
  const match = cleanEmailValue(isoDate).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const formattedTime = formatInterviewTimeForEmail(timeValue);
  if (!match || !formattedTime) return "";
  const year = Number.parseInt(match[1], 10);
  const monthIndex = Number.parseInt(match[2], 10) - 1;
  const day = Number.parseInt(match[3], 10);
  const date = new Date(year, monthIndex, day);
  const weekday = date.toLocaleDateString("en-US", { weekday: "long" });
  const month = date.toLocaleDateString("en-US", { month: "long" });
  return `${weekday}, ${month} ${day}${ordinalSuffix(day)} at ${formattedTime}`;
};

const POTENTIAL_INTERVIEW_ACCESS_DETAILS = {
  Zoom: {
    link: "https://zoom.us/j/7284728472",
    id: "728 472 8472",
    password: "path",
  },
  Meet: {
    link: "https://meet.google.com/zrv-ucir-ugc",
  },
};

const potentialInvitationError = (button, message) => {
  const originalText = button.dataset.originalText || button.textContent;
  button.dataset.originalText = originalText;
  button.textContent = message;
  button.classList.add("is-error");
  window.setTimeout(() => {
    button.textContent = originalText;
    button.classList.remove("is-error");
  }, 2200);
};

const buildPotentialInvitationEmail = (button) => {
  const fullName = cleanEmailValue(button.dataset.fullName);
  const formattedDateTime = formatPotentialInterviewDateTime(button.dataset.interviewDate, button.dataset.interviewTime);
  const platform = cleanEmailValue(button.dataset.platform);
  if (!fullName || !formattedDateTime || !platform) {
    return { error: "Interview details are incomplete." };
  }

  let accessHtml = "";
  let accessText = "";
  if (platform === "Zoom") {
    const { link: zoomLink, id: zoomId, password: zoomPassword } = POTENTIAL_INTERVIEW_ACCESS_DETAILS.Zoom;
    accessText = `The Zoom access details are as follows:\nLink: ${zoomLink}\nZoom ID: ${zoomId}\nPassword: ${zoomPassword}`;
    accessHtml = `
      <div style="margin-top:18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
        <p style="margin:0 0 10px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">The Zoom access details are as follows:</p>
        <p style="margin:0 0 6px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Link: <a href="${escapeEmailAttribute(zoomLink)}" style="color:#00506b;font-weight:700;">${escapeEmailHtml(zoomLink)}</a></p>
        <p style="margin:0 0 6px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Zoom ID: <strong>${escapeEmailHtml(zoomId)}</strong></p>
        <p style="margin:0;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Password: <strong>${escapeEmailHtml(zoomPassword)}</strong></p>
      </div>
    `;
  } else if (platform === "Meet") {
    const { link: meetLink } = POTENTIAL_INTERVIEW_ACCESS_DETAILS.Meet;
    accessText = `The Meet access details are as follows:\nLink: ${meetLink}`;
    accessHtml = `
      <div style="margin-top:18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
        <p style="margin:0 0 10px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">The Meet access details are as follows:</p>
        <p style="margin:0;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Link: <a href="${escapeEmailAttribute(meetLink)}" style="color:#00506b;font-weight:700;">${escapeEmailHtml(meetLink)}</a></p>
      </div>
    `;
  } else {
    return { error: "Interview details are incomplete." };
  }

  const safeName = escapeEmailHtml(fullName);
  const safeDateTime = escapeEmailHtml(formattedDateTime);
  const html = `
    <div style="margin:0;padding:24px;background:#00506b;font-family:Arial, Helvetica, sans-serif;color:#111115;">
      <div style="max-width:620px;margin:0 auto;background:#ffffff;border:1px solid #d9dfdc;border-radius:16px;padding:26px 28px;">
        <p style="display:inline-block;margin:0 0 14px;padding:5px 10px;border-radius:999px;background:#e7f5f8;color:#00506b;font:700 11px Arial, Helvetica, sans-serif;letter-spacing:.5px;text-transform:uppercase;">Interview invitation</p>
        <h1 style="margin:0 0 18px;color:#00506b;font:700 24px/1.25 Arial, Helvetica, sans-serif;">Your interview with Path Examinations</h1>
        <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Dear ${safeName}:</p>
        <p style="margin:0 0 18px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We are pleased to confirm your interview with our team for ${safeDateTime}.</p>
        <div style="margin:0 0 18px;padding:16px 18px;background:#e6f0f3;border-left:4px solid #00506b;border-radius:12px;">
          <p style="margin:0 0 6px;color:#62727a;font:700 11px Arial, Helvetica, sans-serif;letter-spacing:.7px;text-transform:uppercase;">Interview date and time</p>
          <p style="margin:0;color:#00506b;font:700 18px/1.35 Arial, Helvetica, sans-serif;">${safeDateTime}</p>
        </div>
        ${accessHtml}
        <p style="margin:22px 0 0;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Kind regards,</p>
        <p style="margin:4px 0 0;color:#00506b;font:700 15px/1.55 Arial, Helvetica, sans-serif;">Path Examinations</p>
      </div>
    </div>
  `;
  const text = `Dear ${fullName}:\n\nWe are pleased to confirm your interview with our team for ${formattedDateTime}.\n\n${accessText}\n\nKind regards,\n\nPath Examinations`;
  return { html, text };
};

const INTERVIEW_INVITATION_SUBJECT = "Interview invitation: Path International Examinations";

const parseInterviewInvitationDate = (value) => {
  const match = cleanEmailValue(value).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const day = Number.parseInt(match[1], 10);
  const monthIndex = Number.parseInt(match[2], 10) - 1;
  const year = Number.parseInt(match[3], 10);
  const date = new Date(year, monthIndex, day);
  if (Number.isNaN(date.getTime()) || date.getDate() !== day || date.getMonth() !== monthIndex || date.getFullYear() !== year) {
    return null;
  }
  return date;
};

const formatInterviewInvitationDate = (value) => {
  const date = parseInterviewInvitationDate(value);
  if (!date) return "";
  const weekday = date.toLocaleDateString("en-US", { weekday: "long" });
  const month = date.toLocaleDateString("en-US", { month: "long" });
  return `${weekday} ${date.getDate()} ${month} ${date.getFullYear()}`;
};

const getInterviewInvitationOptions = (root) => {
  let rawOptions = [];
  try {
    rawOptions = JSON.parse(root?.dataset.options || "[]");
  } catch (error) {
    rawOptions = [];
  }
  const candidates = Array.isArray(rawOptions) ? rawOptions.slice(0, 5) : [];
  const hasAnyValue = candidates.some((option) => (
    cleanEmailValue(option?.date) ||
    cleanEmailValue(option?.time)
  ));
  if (!hasAnyValue) {
    return { options: [], error: "Interview date and time options are not configured." };
  }
  const options = [];
  for (const option of candidates) {
    const dateValue = cleanEmailValue(option?.date);
    const timeValue = cleanEmailValue(option?.time);
    if (!dateValue && !timeValue) continue;
    const sortDate = parseInterviewInvitationDate(dateValue);
    const displayDate = formatInterviewInvitationDate(dateValue);
    if (!displayDate || !sortDate || !/^([01]\d|2[0-3]):[0-5]\d$/.test(timeValue)) {
      return { options: [], error: "Please complete all interview date and time options before sending the email." };
    }
    options.push({
      label: `${displayDate}, ${timeValue}`,
      sortDate,
      sortTime: timeValue,
    });
  }
  if (!options.length) {
    return { options: [], error: "Interview date and time options are not configured." };
  }
  options.sort((first, second) => first.sortDate - second.sortDate || first.sortTime.localeCompare(second.sortTime));
  return { options };
};

const interviewInvitationPlatformDetails = (platform) => {
  if (platform === "Zoom") {
    const { link, id, password } = POTENTIAL_INTERVIEW_ACCESS_DETAILS.Zoom;
    return {
      label: "Zoom",
      text: `👉 Link: ${link}\n👉 ID de la reunión: ${id}\n👉 Password: ${password}`,
      html: `
        <p style="margin:0 0 6px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">👉 Link: <a href="${escapeEmailAttribute(link)}" style="color:#00506b;font-weight:700;">${escapeEmailHtml(link)}</a></p>
        <p style="margin:0 0 6px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">👉 ID de la reunión: <strong>${escapeEmailHtml(id)}</strong></p>
        <p style="margin:0;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">👉 Password: <strong>${escapeEmailHtml(password)}</strong></p>
      `,
    };
  }
  if (platform === "Meet") {
    const { link } = POTENTIAL_INTERVIEW_ACCESS_DETAILS.Meet;
    return {
      label: "Google Meet",
      text: `👉 Link: ${link}`,
      html: `
        <p style="margin:0;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">👉 Link: <a href="${escapeEmailAttribute(link)}" style="color:#00506b;font-weight:700;">${escapeEmailHtml(link)}</a></p>
      `,
    };
  }
  return null;
};

const buildInterviewInvitationEmail = (button) => {
  const root = button.closest("[data-interview-invitation-email-root]");
  const fullName = cleanEmailValue(root?.dataset.fullName);
  const email = cleanEmailValue(root?.dataset.email);
  const platform = cleanEmailValue(root?.dataset.platform);
  const interviewer = cleanEmailValue(root?.dataset.interviewer) || "our team";
  if (!fullName) return { error: "Potential entry full name is required." };
  if (!email) return { error: "Potential entry email is required." };
  const platformDetails = interviewInvitationPlatformDetails(platform);
  if (!platformDetails) return { error: "Interview platform is not configured." };
  const { options, error } = getInterviewInvitationOptions(root);
  if (error) return { error };

  const optionsText = options.map((option, index) => `Option ${index + 1}: ${option.label}`).join("\n");
  const optionsHtml = options.map((option, index) => `
    <div style="${index > 0 ? "margin-top:12px;padding-top:12px;border-top:1px solid #d9dfdc;" : ""}">
      <p style="margin:0 0 4px;color:#62727a;font:700 11px Arial, Helvetica, sans-serif;text-transform:uppercase;">Option ${index + 1}</p>
      <p style="margin:0;color:#00506b;font:700 17px/1.35 Arial, Helvetica, sans-serif;">${escapeEmailHtml(option.label)}</p>
    </div>
  `).join("");
  const safeName = escapeEmailHtml(fullName);
  const safeInterviewer = escapeEmailHtml(interviewer);
  const bodyHtml = `
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Dear ${safeName},</p>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Thank you for your application at Path International Examinations.</p>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We have reviewed your CV and we believe your profile aligns well with what we are looking for.</p>
    <p style="margin:0 0 16px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We would like to invite you to an initial online interview with ${safeInterviewer}. This will be a great opportunity for us to discuss your experience in more detail and for you to learn more about us.</p>
    <div style="margin:0 0 18px;padding:16px 18px;background:#e6f0f3;border-left:4px solid #00506b;border-radius:12px;">
      <p style="margin:0 0 10px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">Please review the following options and reply to let us know which date and time works best for you:</p>
      ${optionsHtml}
    </div>
    <p style="margin:0 0 18px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">If none of these times work for you, please let me know and we can find an alternative that fits your schedule.</p>
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      <p style="margin:0 0 10px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">Meeting details</p>
      <p style="margin:0 0 12px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">We will be meeting via ${escapeEmailHtml(platformDetails.label)}. You can use the following link to join the interview at your confirmed time:</p>
      ${platformDetails.html}
    </div>
    <p style="margin:0;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We look forward to speaking with you!</p>
  `;
  const html = pathEmailShell({
    label: "Interview invitation",
    title: "Initial online interview invitation",
    bodyHtml,
  });
  const text = `Dear ${fullName},\n\nThank you for your application at Path International Examinations.\n\nWe have reviewed your CV and we believe your profile aligns well with what we are looking for.\n\nWe would like to invite you to an initial online interview with ${interviewer}. This will be a great opportunity for us to discuss your experience in more detail and for you to learn more about us.\n\nPlease review the following options and reply to let us know which date and time works best for you:\n\n${optionsText}\n\nIf none of these times work for you, please let me know and we can find an alternative that fits your schedule.\n\nMeeting details:\nWe will be meeting via ${platformDetails.label}. You can use the following link to join the interview at your confirmed time:\n\n${platformDetails.text}\n\nWe look forward to speaking with you!\n\nBest regards,`;
  return { html, text, email, subject: INTERVIEW_INVITATION_SUBJECT };
};

const showInterviewInvitationEmailStatus = (button, message, isError = false) => {
  const status = button.closest("[data-interview-invitation-email-root]")?.querySelector("[data-interview-invitation-email-status]");
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("is-error", isError);
  window.setTimeout(() => {
    status.textContent = "";
    status.classList.remove("is-error");
  }, isError ? 2600 : 1900);
};

const buildInterviewInvitationGmailUrl = ({ email, subject }) => (
  `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(email)}&su=${encodeURIComponent(subject)}`
);

const initInterviewInvitationEmailButtons = (root = document) => {
  root.querySelectorAll("[data-send-interview-invitation-email]").forEach((button) => {
    if (button.dataset.interviewInvitationSendInitialized === "true") return;
    button.dataset.interviewInvitationSendInitialized = "true";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const payload = buildInterviewInvitationEmail(button);
      if (payload.error) {
        showInterviewInvitationEmailStatus(button, payload.error, true);
        return;
      }
      let copied = false;
      try {
        await copyRichTextToClipboard(payload);
        copied = true;
      } catch (error) {
        copied = false;
      }
      window.open(buildInterviewInvitationGmailUrl(payload), "_blank", "noopener,noreferrer");
      showInterviewInvitationEmailStatus(
        button,
        copied
          ? "Interview invitation copied. Paste it into Gmail to keep the design."
          : "Gmail opened. If the invitation was not copied, use the copy button and paste it manually.",
        !copied,
      );
    });
  });
  root.querySelectorAll("[data-copy-interview-invitation-email]").forEach((button) => {
    if (button.dataset.interviewInvitationCopyInitialized === "true") return;
    button.dataset.interviewInvitationCopyInitialized = "true";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const payload = buildInterviewInvitationEmail(button);
      if (payload.error) {
        showInterviewInvitationEmailStatus(button, payload.error, true);
        return;
      }
      try {
        await copyRichTextToClipboard(payload);
        showInterviewInvitationEmailStatus(button, "Interview invitation email copied.");
      } catch (error) {
        showInterviewInvitationEmailStatus(button, "Could not copy the email. Please try again.", true);
      }
    });
  });
};

const CONTRACT_LINK = "https://drive.google.com/file/d/1FfzKcWq8pED3qv5yuzx2L9n_VEx0ZysM/view?usp=sharing";
const ACCEPTED_APPLICATION_SUBJECT = "Your application has been accepted";

const formatInductionSessionDate = (value) => {
  const match = cleanEmailValue(value).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return "";
  const day = Number.parseInt(match[1], 10);
  const monthIndex = Number.parseInt(match[2], 10) - 1;
  const year = Number.parseInt(match[3], 10);
  const date = new Date(year, monthIndex, day);
  if (Number.isNaN(date.getTime()) || date.getDate() !== day || date.getMonth() !== monthIndex || date.getFullYear() !== year) {
    return "";
  }
  const weekday = date.toLocaleDateString("en-US", { weekday: "long" });
  const month = date.toLocaleDateString("en-US", { month: "long" });
  return `${weekday} ${day} ${month} ${year}`;
};

const formatInductionTimeRange = (startTime, endTime) => {
  const start = cleanEmailValue(startTime);
  const end = cleanEmailValue(endTime);
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(start) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(end)) {
    return "";
  }
  return `${start}–${end}`;
};

const parseInductionSessionSortDate = (value) => {
  const match = cleanEmailValue(value).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const day = Number.parseInt(match[1], 10);
  const monthIndex = Number.parseInt(match[2], 10) - 1;
  const year = Number.parseInt(match[3], 10);
  const date = new Date(year, monthIndex, day);
  if (Number.isNaN(date.getTime()) || date.getDate() !== day || date.getMonth() !== monthIndex || date.getFullYear() !== year) {
    return null;
  }
  return date;
};

const getInductionSessionOptions = (button) => {
  let rawOptions = [];
  try {
    rawOptions = JSON.parse(button.dataset.inductionOptions || "[]");
  } catch (error) {
    rawOptions = [];
  }
  if (!Array.isArray(rawOptions) || rawOptions.length === 0) {
    rawOptions = [{
      date: button.dataset.inductionDate,
      start_time: button.dataset.inductionStartTime,
      end_time: button.dataset.inductionEndTime,
    }];
  }
  const candidates = rawOptions.filter((option) => option && typeof option === "object");
  const hasAnyValue = candidates.some((option) => cleanEmailValue(option.date) || cleanEmailValue(option.start_time) || cleanEmailValue(option.end_time));
  if (!hasAnyValue) {
    return { options: [], error: "Upcoming induction session date and time options are not configured." };
  }
  const options = [];
  for (const option of candidates) {
    const sortDate = parseInductionSessionSortDate(option.date);
    const inductionDate = formatInductionSessionDate(option.date);
    const inductionTimeRange = formatInductionTimeRange(option.start_time, option.end_time);
    const startTime = cleanEmailValue(option.start_time);
    const endTime = cleanEmailValue(option.end_time);
    if (!sortDate || !inductionDate || !inductionTimeRange || startTime >= endTime) {
      return { options: [], error: "Upcoming induction session date and time options are not configured." };
    }
    options.push({ date: inductionDate, timeRange: inductionTimeRange, sortDate, startTime });
  }
  options.sort((first, second) => first.sortDate - second.sortDate || first.startTime.localeCompare(second.startTime));
  return { options };
};

const pathEmailShell = ({ label, title, bodyHtml }) => `
  <div style="margin:0;padding:24px;background:#00506b;font-family:Arial, Helvetica, sans-serif;color:#111115;">
    <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #d9dfdc;border-radius:16px;padding:26px 28px;">
      <p style="display:inline-block;margin:0 0 14px;padding:5px 10px;border-radius:999px;background:#e7f5f8;color:#00506b;font:700 11px Arial, Helvetica, sans-serif;letter-spacing:.5px;text-transform:uppercase;">${escapeEmailHtml(label)}</p>
      <h1 style="margin:0 0 18px;color:#00506b;font:700 24px/1.25 Arial, Helvetica, sans-serif;">${escapeEmailHtml(title)}</h1>
      ${bodyHtml}
      <p style="margin:22px 0 0;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Best regards,</p>
      <p style="margin:4px 0 0;color:#00506b;font:700 15px/1.55 Arial, Helvetica, sans-serif;">Path International Examinations</p>
    </div>
  </div>
`;

const getEntryAcceptedPreassignedSessions = (source) => {
  let rawSessions = [];
  try {
    rawSessions = JSON.parse(source?.dataset?.preassignedExamSessions || "[]");
  } catch (error) {
    rawSessions = [];
  }
  if (!Array.isArray(rawSessions)) return [];
  return rawSessions
    .filter((session) => session && typeof session === "object")
    .map((session, index) => ({
      name: cleanEmailValue(session.name),
      date: cleanEmailValue(session.date),
      format: cleanEmailValue(session.format),
      address: cleanEmailValue(session.address),
      sortDate: Date.parse(cleanEmailValue(session.date)) || 0,
      index,
    }))
    .filter((session) => session.name && session.date && session.format)
    .sort((first, second) => first.sortDate - second.sortDate || first.index - second.index);
};

const entryAcceptedExamSessionHtml = (session) => {
  const isOnsite = session.format === "Onsite";
  return `
    <div style="margin:0 0 10px;padding:12px 14px;background:#ffffff;border:1px solid #d9dfdc;border-radius:10px;">
      <p style="margin:0;color:#00506b;font:700 15px/1.35 Arial, Helvetica, sans-serif;">${escapeEmailHtml(session.name)}</p>
      <p style="margin:4px 0 0;color:#111115;font:400 14px/1.45 Arial, Helvetica, sans-serif;">${escapeEmailHtml(session.date)}</p>
      <p style="margin:2px 0 0;color:#53615c;font:700 13px/1.4 Arial, Helvetica, sans-serif;">${isOnsite ? "Onsite session" : "Online session"}</p>
      ${isOnsite && session.address ? `<p style="margin:2px 0 0;color:#111115;font:400 13px/1.45 Arial, Helvetica, sans-serif;">${escapeEmailHtml(session.address)}</p>` : ""}
    </div>
  `;
};

const entryAcceptedExamSessionText = (session) => {
  const lines = [
    session.name,
    session.date,
    session.format === "Onsite" ? "Onsite session" : "Online session",
  ];
  if (session.format === "Onsite" && session.address) lines.push(session.address);
  return lines.join("\n");
};

const getEntryAcceptedCertificationProgrammes = (source) => {
  let payload = {};
  try {
    payload = JSON.parse(source?.dataset?.certificationProgrammes || "{}");
  } catch (error) {
    payload = {};
  }
  const roles = Array.isArray(payload.roles)
    ? payload.roles.map(cleanEmailValue).filter((role) => role === "Examiner" || role === "Supervisor")
    : [];
  const programmeByRole = {};
  if (Array.isArray(payload.programmes)) {
    payload.programmes.forEach((programme) => {
      if (!programme || typeof programme !== "object") return;
      const role = cleanEmailValue(programme.role);
      if (role !== "Examiner" && role !== "Supervisor") return;
      programmeByRole[role] = {
        role,
        remoteTrainingPeriod: cleanEmailValue(programme.remote_training_period || programme.remoteTrainingPeriod),
        annualMeeting: cleanEmailValue(programme.annual_meeting || programme.annualMeeting),
      };
    });
  }
  const orderedRoles = ["Examiner", "Supervisor"].filter((role) => roles.includes(role));
  return orderedRoles.map((role) => programmeByRole[role] || {
    role,
    remoteTrainingPeriod: "",
    annualMeeting: "",
  });
};

const validateEntryAcceptedCertificationProgrammes = (programmes) => {
  if (!programmes.length) return "Potential entry role is required.";
  const examinerProgramme = programmes.find((programme) => programme.role === "Examiner");
  if (examinerProgramme && (!examinerProgramme.remoteTrainingPeriod || !examinerProgramme.annualMeeting)) {
    return "Examiner certification dates are not configured.";
  }
  const supervisorProgramme = programmes.find((programme) => programme.role === "Supervisor");
  if (supervisorProgramme && (!supervisorProgramme.remoteTrainingPeriod || !supervisorProgramme.annualMeeting)) {
    return "Supervisor certification dates are not configured.";
  }
  return "";
};

const entryAcceptedCertificationProgrammeHtml = (programme) => `
  <div style="margin:0 0 12px;padding:12px 14px;background:#ffffff;border:1px solid #d9dfdc;border-radius:10px;">
    <p style="margin:0 0 8px;color:#00506b;font:700 13px/1.35 Arial, Helvetica, sans-serif;letter-spacing:.3px;text-transform:uppercase;">${escapeEmailHtml(programme.role)} CERTIFICATION</p>
    <ul style="margin:0;padding-left:20px;color:#111115;font:400 14px/1.55 Arial, Helvetica, sans-serif;">
      <li style="margin-bottom:6px;"><strong>Remote training period:</strong> ${escapeEmailHtml(programme.remoteTrainingPeriod)}</li>
      <li><strong>Annual meeting:</strong> ${escapeEmailHtml(programme.annualMeeting)}</li>
    </ul>
  </div>
`;

const entryAcceptedCertificationProgrammeText = (programme) => (
  `${programme.role.toUpperCase()} CERTIFICATION\n\n`
  + `* Remote training period: ${programme.remoteTrainingPeriod}\n`
  + `* Annual meeting: ${programme.annualMeeting}`
);

const ENTRY_ACCEPTED_CERTIFICATION_NOTE = "Further information, such as platform access details and any other relevant instructions, will be provided in due course.";
const STAFF_SESSIONS_TIME_SLOTS_NOTE = "At this stage, we are unable to confirm further details, such as time slots or fees, as the final schedule will only be available once candidate registration closes in October.";
const STAFF_SESSIONS_CERTIFICATION_NOTE = "Further information, such as platform access details and any other relevant instructions, will be provided in due course.";

const getStaffSessionsEmailPayload = (button) => {
  try {
    const payload = JSON.parse(button?.dataset?.staffSessionsEmailPayload || "{}");
    return payload && typeof payload === "object" ? payload : {};
  } catch (error) {
    return {};
  }
};

const staffSessionsEmailProgrammes = (payload) => {
  const programmesPayload = payload?.certification_programmes || payload?.certificationProgrammes || {};
  const roles = Array.isArray(programmesPayload.roles)
    ? programmesPayload.roles.map(cleanEmailValue).filter((role) => role === "Examiner" || role === "Supervisor")
    : [];
  const programmeByRole = {};
  if (Array.isArray(programmesPayload.programmes)) {
    programmesPayload.programmes.forEach((programme) => {
      if (!programme || typeof programme !== "object") return;
      const role = cleanEmailValue(programme.role);
      if (role !== "Examiner" && role !== "Supervisor") return;
      programmeByRole[role] = {
        role,
        remoteTrainingPeriod: cleanEmailValue(programme.remote_training_period || programme.remoteTrainingPeriod),
        annualMeeting: cleanEmailValue(programme.annual_meeting || programme.annualMeeting),
      };
    });
  }
  return ["Examiner", "Supervisor"]
    .filter((role) => roles.includes(role))
    .map((role) => programmeByRole[role] || { role, remoteTrainingPeriod: "", annualMeeting: "" });
};

const staffSessionsEmailTitle = (payload) => {
  const explicitYear = cleanEmailValue(payload?.session_year || payload?.sessionYear);
  if (/^\d{4}$/.test(explicitYear)) {
    return `${explicitYear} Path exam sessions and training programmes`;
  }
  const sessions = Array.isArray(payload?.sessions) ? payload.sessions : [];
  const years = Array.from(new Set(sessions
    .map((session) => cleanEmailValue(session?.date).match(/\b(\d{4})\b/)?.[1] || "")
    .filter((year) => /^\d{4}$/.test(year))))
    .sort();
  if (years.length === 1) return `${years[0]} Path exam sessions and training programmes`;
  if (years.length > 1) return `${years[0]}–${years[years.length - 1]} Path exam sessions and training programmes`;
  return "Path exam sessions and training programmes";
};

const validateStaffSessionsEmailPayload = (payload) => {
  const fullName = cleanEmailValue(payload?.full_name || payload?.fullName);
  if (!fullName) return "Staff member full name is required.";
  const sessions = Array.isArray(payload?.sessions) ? payload.sessions : [];
  if (!sessions.length) return "No assigned exam sessions available for this staff member.";
  const missingSessionData = sessions.some((session) => {
    const roles = Array.isArray(session?.roles) ? session.roles.map(cleanEmailValue).filter(Boolean) : [];
    const format = cleanEmailValue(session?.format);
    return !cleanEmailValue(session?.name) || !cleanEmailValue(session?.date) || !roles.length || !format;
  });
  if (missingSessionData) return "Some assigned exam sessions are missing required information.";
  const programmes = staffSessionsEmailProgrammes(payload);
  const examinerProgramme = programmes.find((programme) => programme.role === "Examiner");
  if (examinerProgramme && (!examinerProgramme.remoteTrainingPeriod || !examinerProgramme.annualMeeting)) {
    return "Examiner certification dates are not configured.";
  }
  const supervisorProgramme = programmes.find((programme) => programme.role === "Supervisor");
  if (supervisorProgramme && (!supervisorProgramme.remoteTrainingPeriod || !supervisorProgramme.annualMeeting)) {
    return "Supervisor certification dates are not configured.";
  }
  return "";
};

const staffSessionsEmailSessionHtml = (session, index) => {
  const roles = Array.isArray(session.roles) ? session.roles.map(cleanEmailValue).filter(Boolean).join(", ") : "";
  const format = cleanEmailValue(session.format);
  const shift = cleanEmailValue(session.shift);
  const address = format === "Onsite"
    ? cleanEmailValue(session.address) || "Address to be confirmed."
    : "";
  return `
    <div style="margin:${index > 0 ? "12px 0 0" : "0"};padding:${index > 0 ? "12px 0 0" : "0"};${index > 0 ? "border-top:1px solid #d9dfdc;" : ""}">
      <p style="margin:0 0 8px;color:#00506b;font:700 14px/1.45 Arial, Helvetica, sans-serif;"><strong>Exam session ${index + 1}: ${escapeEmailHtml(session.name)}</strong></p>
      <p style="margin:0 0 5px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;"><strong>Date:</strong> ${escapeEmailHtml(session.date)}</p>
      ${shift ? `<p style="margin:0 0 5px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;"><strong>Shift:</strong> ${escapeEmailHtml(shift)}</p>` : ""}
      <p style="margin:0 0 5px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;"><strong>Role:</strong> ${escapeEmailHtml(roles)}</p>
      <p style="margin:0${address ? " 0 5px" : ""};color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;"><strong>Format:</strong> ${escapeEmailHtml(format)}</p>
      ${address ? `<p style="margin:0;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;"><strong>Address:</strong> ${escapeEmailHtml(address)}</p>` : ""}
    </div>
  `;
};

const staffSessionsEmailSessionText = (session, index) => {
  const roles = Array.isArray(session.roles) ? session.roles.map(cleanEmailValue).filter(Boolean).join(", ") : "";
  const format = cleanEmailValue(session.format);
  const shift = cleanEmailValue(session.shift);
  const address = format === "Onsite"
    ? cleanEmailValue(session.address) || "Address to be confirmed."
    : "";
  return [
    `Exam session ${index + 1}: ${cleanEmailValue(session.name)}`,
    `Date: ${cleanEmailValue(session.date)}`,
    shift ? `Shift: ${shift}` : "",
    `Role: ${roles}`,
    `Format: ${format}`,
    address ? `Address: ${address}` : "",
  ].filter(Boolean).join("\n");
};

const staffSessionsCertificationProgrammeHtml = (programme) => `
  <div style="margin:0 0 12px;padding:12px 14px;background:#ffffff;border:1px solid #d9dfdc;border-radius:10px;">
    <p style="margin:0 0 8px;color:#00506b;font:700 13px/1.35 Arial, Helvetica, sans-serif;letter-spacing:.3px;text-transform:uppercase;">${escapeEmailHtml(programme.role)} CERTIFICATION</p>
    <ul style="margin:0;padding-left:20px;color:#111115;font:400 14px/1.55 Arial, Helvetica, sans-serif;">
      <li style="margin-bottom:6px;"><strong>Remote training period:</strong> ${escapeEmailHtml(programme.remoteTrainingPeriod)}</li>
      <li><strong>Annual meeting:</strong> ${escapeEmailHtml(programme.annualMeeting)}</li>
    </ul>
  </div>
`;

const staffSessionsCertificationProgrammeText = (programme) => (
  `${programme.role.toUpperCase()} CERTIFICATION\n\n`
  + `* Remote training period: ${programme.remoteTrainingPeriod}\n`
  + `* Annual meeting: ${programme.annualMeeting}`
);

const buildStaffSessionsEmail = (button) => {
  const payload = getStaffSessionsEmailPayload(button);
  const validationError = validateStaffSessionsEmailPayload(payload);
  if (validationError) return { error: validationError };
  const fullName = cleanEmailValue(payload.full_name || payload.fullName);
  const emailTitle = staffSessionsEmailTitle(payload);
  const sessions = payload.sessions;
  const programmes = staffSessionsEmailProgrammes(payload);
  const hasCertificationProgrammes = programmes.length > 0;
  const sessionsHtml = sessions.map(staffSessionsEmailSessionHtml).join("");
  const sessionsText = sessions.map(staffSessionsEmailSessionText).join("\n\n");
  const certificationHtml = hasCertificationProgrammes ? `
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      <p style="margin:0 0 12px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">2. CONFIRM ANNUAL CERTIFICATION PROGRAMMES:</p>
      ${programmes.map(staffSessionsCertificationProgrammeHtml).join("")}
      <p style="margin:12px 0 0;color:#53615c;font:400 14px/1.55 Arial, Helvetica, sans-serif;">${escapeEmailHtml(STAFF_SESSIONS_CERTIFICATION_NOTE)}</p>
    </div>
  ` : "";
  const certificationText = hasCertificationProgrammes
    ? `\n\n2. CONFIRM ANNUAL CERTIFICATION PROGRAMMES:\n\n${programmes.map(staffSessionsCertificationProgrammeText).join("\n\n")}\n\n${STAFF_SESSIONS_CERTIFICATION_NOTE}`
    : "";
  const reviewSentence = hasCertificationProgrammes
    ? "Please review the information above and reply to this email pre-confirming your availability for the assigned exam sessions and training programmes."
    : "Please review the information above and reply to this email pre-confirming your availability for the assigned exam sessions.";
  const reviewSentenceHtml = hasCertificationProgrammes
    ? `Please review the information above and reply to this email <strong>${escapeEmailHtml("pre-confirming your availability for the assigned exam sessions and training programmes")}</strong>.`
    : escapeEmailHtml(reviewSentence);
  const bodyHtml = `
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Dear ${escapeEmailHtml(fullName)},</p>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We hope you have had a great start to the year.</p>
    <p style="margin:0 0 18px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We are writing to share important information regarding the upcoming Path Examinations cycle, including your assigned exam sessions${hasCertificationProgrammes ? " as well as key training programmes" : ""}.</p>
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      <p style="margin:0 0 12px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">1. PRE-CONFIRM YOUR PARTICIPATION IN EXAM SESSIONS:</p>
      ${sessionsHtml}
      <p style="margin:12px 0 0;color:#111115;font:400 14px/1.55 Arial, Helvetica, sans-serif;">${escapeEmailHtml(STAFF_SESSIONS_TIME_SLOTS_NOTE)}</p>
    </div>
    ${certificationHtml}
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">${reviewSentenceHtml} In the unlikely event of any changes (e.g. exam session cancellations), these will be replaced by online exam sessions.</p>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Thank you in advance for your collaboration. We look forward to working together towards a successful and well-organised exam cycle.</p>
  `;
  const html = pathEmailShell({
    label: "Exam session cycle",
    title: emailTitle,
    bodyHtml,
  });
  const text = `Exam session cycle\n${emailTitle}\n\nDear ${fullName},\n\nWe hope you have had a great start to the year.\n\nWe are writing to share important information regarding the upcoming Path Examinations cycle, including your assigned exam sessions${hasCertificationProgrammes ? " as well as key training programmes" : ""}.\n\n1. PRE-CONFIRM YOUR PARTICIPATION IN EXAM SESSIONS:\n\n${sessionsText}\n\n${STAFF_SESSIONS_TIME_SLOTS_NOTE}${certificationText}\n\n${reviewSentence} In the unlikely event of any changes (e.g. exam session cancellations), these will be replaced by online exam sessions.\n\nThank you in advance for your collaboration. We look forward to working together towards a successful and well-organised exam cycle.`;
  return { html, text };
};

const showStaffSessionsEmailCopyFeedback = (button, message, isError = false) => {
  const feedback = button.querySelector(".copy-button-feedback");
  if (feedback) feedback.textContent = message;
  button.classList.toggle("is-error", isError);
  button.classList.toggle("is-copied", !isError);
  window.setTimeout(() => {
    button.classList.remove("is-error", "is-copied");
    if (feedback) feedback.textContent = "Copied";
  }, isError ? 2600 : 1800);
};

const initStaffSessionsEmailCopyButtons = (root = document) => {
  root.querySelectorAll("[data-staff-sessions-copy-email]").forEach((button) => {
    if (button.dataset.staffSessionsCopyInitialized === "true") return;
    button.dataset.staffSessionsCopyInitialized = "true";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      if (button.disabled) return;
      const payload = buildStaffSessionsEmail(button);
      if (payload.error) {
        showStaffSessionsEmailCopyFeedback(button, payload.error, true);
        return;
      }
      try {
        await copyRichTextToClipboard(payload);
        showStaffSessionsEmailCopyFeedback(button, "Sessions email copied.");
      } catch (error) {
        showStaffSessionsEmailCopyFeedback(button, "Could not copy the sessions email. Please try again.", true);
      }
    });
  });
};

if (typeof document !== "undefined") initStaffSessionsEmailCopyButtons();

const STAFF_PRECONFIRMATION_STATUS = "⏳ Participation awaiting your pre-confirmation";

const parseStaffPreconfirmationPayload = (button) => {
  try {
    const payload = JSON.parse(button?.dataset?.staffPreconfirmationEmailPayload || "{}");
    return payload && typeof payload === "object" ? payload : {};
  } catch (error) {
    return {};
  }
};

const staffPreconfirmationRoleFromSection = (sectionKey) => {
  const normalized = cleanEmailValue(sectionKey).toLowerCase();
  if (normalized === "supervisor") return "Supervisor";
  if (normalized === "examiner") return "Examiner";
  if (normalized === "intern") return "Intern";
  return "";
};

const getStaffPreconfirmationEmailPayload = (button) => {
  const explicitPayload = parseStaffPreconfirmationPayload(button);
  if (Object.keys(explicitPayload).length) return explicitPayload;
  const row = button?.closest?.("[data-supervisor-row]");
  const panel = button?.closest?.("[data-session-modal-panel]");
  const select = row?.querySelector?.("[data-team-member-select]");
  const option = selectedTeamMemberOption(select);
  let certifications = {};
  try {
    certifications = JSON.parse(panel?.dataset?.preconfirmationCertifications || "{}");
  } catch (error) {
    certifications = {};
  }
  return {
    full_name: cleanEmailValue(option?.dataset?.name) || cleanEmailValue(row?.querySelector?.("[data-staff-card-title]")?.textContent),
    role: staffPreconfirmationRoleFromSection(row?.dataset?.sectionKey),
    session_name: cleanEmailValue(panel?.dataset?.sessionName),
    session_date: cleanEmailValue(panel?.dataset?.sessionDateEmail || panel?.dataset?.sessionDateLabel),
    shift: cleanEmailValue(panel?.dataset?.sessionShift),
    format: cleanEmailValue(panel?.dataset?.sessionFormat),
    address: cleanEmailValue(panel?.dataset?.sessionAddress),
    certifications,
  };
};

const staffPreconfirmationCertificationForRole = (payload, role) => {
  const certifications = payload?.certifications && typeof payload.certifications === "object"
    ? payload.certifications
    : {};
  const programme = certifications[role] || certifications[role?.toLowerCase?.()] || {};
  return {
    role,
    remoteTrainingPeriod: cleanEmailValue(programme.remote_training_period || programme.remoteTrainingPeriod),
    annualMeeting: cleanEmailValue(programme.annual_meeting || programme.annualMeeting),
  };
};

const validateStaffPreconfirmationEmailPayload = (payload) => {
  const fullName = cleanEmailValue(payload?.full_name || payload?.fullName);
  if (!fullName) return "Staff member full name is required.";
  const role = cleanEmailValue(payload?.role);
  const sessionName = cleanEmailValue(payload?.session_name || payload?.sessionName);
  const sessionDate = cleanEmailValue(payload?.session_date || payload?.sessionDate);
  const format = cleanEmailValue(payload?.format);
  if (!role || !sessionName || !sessionDate || !format) return "Exam session information is incomplete.";
  if (format === "Onsite" && !cleanEmailValue(payload?.address)) {
    return "Exam session address is required for onsite sessions.";
  }
  if (role === "Examiner" || role === "Supervisor") {
    const programme = staffPreconfirmationCertificationForRole(payload, role);
    if (!programme.remoteTrainingPeriod || !programme.annualMeeting) {
      return `${role} certification dates are not configured.`;
    }
  }
  return "";
};

const staffPreconfirmationSessionDetailsHtml = (payload) => {
  const format = cleanEmailValue(payload.format);
  const shift = cleanEmailValue(payload.shift);
  const address = format === "Onsite" ? cleanEmailValue(payload.address) : "";
  const lines = [
    ["Exam session:", cleanEmailValue(payload.session_name || payload.sessionName)],
    ["Date:", cleanEmailValue(payload.session_date || payload.sessionDate)],
    shift ? ["Shift:", shift] : null,
    ["Format:", format],
    address ? ["Address:", address] : null,
  ].filter(Boolean);
  return `
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      ${lines.map(([label, value]) => `<p style="margin:0 0 6px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;"><strong>${escapeEmailHtml(label)}</strong> ${escapeEmailHtml(value)}</p>`).join("")}
    </div>
  `;
};

const staffPreconfirmationSessionDetailsText = (payload) => {
  const format = cleanEmailValue(payload.format);
  const shift = cleanEmailValue(payload.shift);
  const address = format === "Onsite" ? cleanEmailValue(payload.address) : "";
  return [
    `Exam session: ${cleanEmailValue(payload.session_name || payload.sessionName)}`,
    `Date: ${cleanEmailValue(payload.session_date || payload.sessionDate)}`,
    shift ? `Shift: ${shift}` : "",
    `Format: ${format}`,
    address ? `Address: ${address}` : "",
  ].filter(Boolean).join("\n");
};

const staffPreconfirmationCertificationHtml = (programme) => `
  <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
    <p style="margin:0 0 10px;color:#00506b;font:700 13px/1.35 Arial, Helvetica, sans-serif;letter-spacing:.3px;text-transform:uppercase;">${escapeEmailHtml(programme.role.toUpperCase())} CERTIFICATION</p>
    <ul style="margin:0;padding-left:20px;color:#111115;font:400 14px/1.55 Arial, Helvetica, sans-serif;">
      <li style="margin-bottom:6px;"><strong>Remote training period:</strong> ${escapeEmailHtml(programme.remoteTrainingPeriod)}</li>
      <li><strong>Annual meeting:</strong> ${escapeEmailHtml(programme.annualMeeting)}</li>
    </ul>
  </div>
`;

const staffPreconfirmationCertificationText = (programme) => (
  `${programme.role.toUpperCase()} CERTIFICATION\n\n`
  + `* Remote training period: ${programme.remoteTrainingPeriod}\n`
  + `* Annual meeting: ${programme.annualMeeting}`
);

const buildStaffPreconfirmationEmail = (button) => {
  const payload = getStaffPreconfirmationEmailPayload(button);
  const validationError = validateStaffPreconfirmationEmailPayload(payload);
  if (validationError) return { error: validationError };
  const fullName = cleanEmailValue(payload.full_name || payload.fullName);
  const role = cleanEmailValue(payload.role);
  const hasCertification = role === "Examiner" || role === "Supervisor";
  const programme = hasCertification ? staffPreconfirmationCertificationForRole(payload, role) : null;
  const certificationHtml = programme ? staffPreconfirmationCertificationHtml(programme) : "";
  const certificationText = programme ? staffPreconfirmationCertificationText(programme) : "";
  const trainingIntro = hasCertification
    ? "We would also like to remind you of the dates and times of the training programme for this role:"
    : "";
  const reviewSentence = hasCertification
    ? "Please review the information above and reply to this email pre-confirming your availability for the assigned exam session and training programme. In the unlikely event of any changes (e.g. exam session cancellation), this will be replaced by an online exam session."
    : "Please review the information above and reply to this email pre-confirming your availability for the assigned exam session. In the unlikely event of any changes (e.g. exam session cancellation), this will be replaced by an online exam session.";
  const reviewSentenceHtml = hasCertification
    ? `Please review the information above and reply to this email <strong>${escapeEmailHtml("pre-confirming your availability for the assigned exam session and training programme")}</strong>. In the unlikely event of any changes (e.g. exam session cancellation), this will be replaced by an online exam session.`
    : escapeEmailHtml(reviewSentence);
  const bodyHtml = `
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Dear ${escapeEmailHtml(fullName)},</p>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Hope you’re doing very well.</p>
    <p style="display:inline-block;margin:0 0 16px;padding:6px 11px;border-radius:999px;background:#fff3c4;color:#6f5100;font:700 12px Arial, Helvetica, sans-serif;">${escapeEmailHtml(STAFF_PRECONFIRMATION_STATUS)}</p>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We are pleased to inform you that you have been pre-selected as a <strong>${escapeEmailHtml(role)}</strong> for the upcoming Path exam session, subject to your pre-confirmation:</p>
    ${staffPreconfirmationSessionDetailsHtml(payload)}
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">${escapeEmailHtml(STAFF_SESSIONS_TIME_SLOTS_NOTE)}</p>
    ${hasCertification ? `<p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">${escapeEmailHtml(trainingIntro)}</p>${certificationHtml}<p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">${escapeEmailHtml(STAFF_SESSIONS_CERTIFICATION_NOTE)}</p>` : ""}
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">${reviewSentenceHtml}</p>
    <p style="margin:0;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Thank you in advance for your collaboration. We look forward to working together towards a successful and well-organised exam cycle.</p>
  `;
  const html = pathEmailShell({
    label: "Pre-confirmation",
    title: "Path exam session pre-confirmation",
    bodyHtml,
  });
  const text = [
    "Pre-confirmation",
    "Path exam session pre-confirmation",
    "",
    `Dear ${fullName},`,
    "",
    "Hope you’re doing very well.",
    "",
    STAFF_PRECONFIRMATION_STATUS,
    "",
    `We are pleased to inform you that you have been pre-selected as a ${role} for the upcoming Path exam session, subject to your pre-confirmation:`,
    "",
    staffPreconfirmationSessionDetailsText(payload),
    "",
    STAFF_SESSIONS_TIME_SLOTS_NOTE,
    hasCertification ? `\n${trainingIntro}\n\n${certificationText}\n\n${STAFF_SESSIONS_CERTIFICATION_NOTE}` : "",
    "",
    reviewSentence,
    "",
    "Thank you in advance for your collaboration. We look forward to working together towards a successful and well-organised exam cycle.",
  ].filter((line) => line !== "").join("\n");
  return { html, text };
};

const showStaffPreconfirmationEmailFeedback = (button, message, isError = false) => {
  const originalText = button.dataset.originalText || button.textContent;
  button.dataset.originalText = originalText;
  button.textContent = message;
  button.classList.toggle("is-error", isError);
  button.classList.toggle("is-copied", !isError);
  window.setTimeout(() => {
    button.textContent = originalText;
    button.classList.remove("is-error", "is-copied");
  }, isError ? 2800 : 1900);
};

const initStaffPreconfirmationEmailButtons = (root = document) => {
  root.querySelectorAll("[data-staff-preconfirmation-email]").forEach((button) => {
    if (button.dataset.staffPreconfirmationInitialized === "true") return;
    button.dataset.staffPreconfirmationInitialized = "true";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      if (button.disabled) return;
      const payload = buildStaffPreconfirmationEmail(button);
      if (payload.error) {
        showStaffPreconfirmationEmailFeedback(button, payload.error, true);
        return;
      }
      try {
        await copyRichTextToClipboard(payload);
        showStaffPreconfirmationEmailFeedback(button, "Pre-confirmation email copied.");
      } catch (error) {
        showStaffPreconfirmationEmailFeedback(button, "Could not copy the pre-confirmation email. Please try again.", true);
      }
    });
  });
};

if (typeof document !== "undefined") initStaffPreconfirmationEmailButtons();

const buildSuccessfulApplicationEmail = (button) => {
  const source = button?.dataset?.fullName
    ? button
    : button?.closest?.("[data-entry-accepted-email-root]") || button;
  const fullName = cleanEmailValue(source.dataset.fullName);
  if (!fullName) return { error: "Potential entry full name is required." };
  const { options: inductionOptions, error: inductionOptionsError } = getInductionSessionOptions(source);
  if (inductionOptionsError) {
    return { error: inductionOptionsError };
  }
  if (!inductionOptions.length) {
    return { error: "Upcoming induction session date and time options are not configured." };
  }
  const { link: zoomLink, id: zoomId, password: zoomPassword } = POTENTIAL_INTERVIEW_ACCESS_DETAILS.Zoom;
  const safeName = escapeEmailHtml(fullName);
  const preassignedSessions = getEntryAcceptedPreassignedSessions(source);
  const hasPreassignedSessions = preassignedSessions.length > 0;
  const inductionStepNumber = hasPreassignedSessions ? 3 : 2;
  const certificationStepNumber = inductionStepNumber + 1;
  const certificationProgrammes = getEntryAcceptedCertificationProgrammes(source);
  const certificationError = validateEntryAcceptedCertificationProgrammes(certificationProgrammes);
  if (certificationError) {
    return { error: certificationError };
  }
  const inductionOptionsHtml = inductionOptions.map((option, index) => `
      <div style="${index > 0 ? "margin-top:12px;padding-top:12px;border-top:1px solid #d9dfdc;" : ""}">
        <p style="margin:0 0 4px;color:#62727a;font:700 11px Arial, Helvetica, sans-serif;text-transform:uppercase;">Option ${index + 1}:</p>
        <p style="margin:0;color:#00506b;font:700 18px/1.35 Arial, Helvetica, sans-serif;">${escapeEmailHtml(option.date)}</p>
        <p style="margin:3px 0 0;color:#00506b;font:700 18px/1.35 Arial, Helvetica, sans-serif;">${escapeEmailHtml(option.timeRange)}</p>
      </div>
    `).join("");
  const inductionOptionsText = inductionOptions
    .map((option, index) => `Option ${index + 1}:\n${option.date}\n${option.timeRange}`)
    .join("\n\n");
  const preassignedSessionsHtml = hasPreassignedSessions ? `
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      <p style="margin:0 0 12px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">2. PRE-CONFIRM YOUR PARTICIPATION IN EXAM SESSIONS:</p>
      ${preassignedSessions.map(entryAcceptedExamSessionHtml).join("")}
      <p style="margin:12px 0 0;color:#111115;font:400 14px/1.55 Arial, Helvetica, sans-serif;">At this stage, we are unable to confirm further details, such as time slots or fees, as the final schedule will only be available once candidate registration closes in October.</p>
    </div>
  ` : "";
  const preassignedSessionsText = hasPreassignedSessions
    ? `\n\n2. PRE-CONFIRM YOUR PARTICIPATION IN EXAM SESSIONS:\n\n${preassignedSessions.map(entryAcceptedExamSessionText).join("\n\n")}\n\nAt this stage, we are unable to confirm further details, such as time slots or fees, as the final schedule will only be available once candidate registration closes in October.`
    : "";
  const certificationProgrammesHtml = `
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      <p style="margin:0 0 12px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">${certificationStepNumber}. CONFIRM ANNUAL CERTIFICATION PROGRAMMES:</p>
      ${certificationProgrammes.map(entryAcceptedCertificationProgrammeHtml).join("")}
      <p style="margin:12px 0 0;color:#53615c;font:400 14px/1.55 Arial, Helvetica, sans-serif;">${escapeEmailHtml(ENTRY_ACCEPTED_CERTIFICATION_NOTE)}</p>
    </div>
  `;
  const certificationProgrammesText = `\n\n${certificationStepNumber}. CONFIRM ANNUAL CERTIFICATION PROGRAMMES:\n\n${certificationProgrammes.map(entryAcceptedCertificationProgrammeText).join("\n\n")}\n\n${ENTRY_ACCEPTED_CERTIFICATION_NOTE}`;
  const bodyHtml = `
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Dear ${safeName},</p>
    <p style="margin:0 0 16px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We are delighted to inform you that your application for the role of <strong>Examiner</strong> at Path International Examinations has been accepted. We are confident that you will be a valuable addition to our academic team.</p>
    <p style="margin:0 0 18px;color:#111115;font:700 15px/1.55 Arial, Helvetica, sans-serif;">To formally accept this offer and secure your place, please complete the following steps within 3 working days:</p>
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      <p style="margin:0 0 12px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">1. SEND THESE FILES TO <a href="mailto:admin@pathexaminations.com" style="color:#00506b;font-weight:700;">ADMIN@PATHEXAMINATIONS.COM</a>:</p>
      <ul style="margin:0;padding-left:20px;color:#111115;font:400 14px/1.55 Arial, Helvetica, sans-serif;">
        <li style="margin-bottom:8px;"><a href="${escapeEmailAttribute(CONTRACT_LINK)}" style="color:#00506b;font-weight:700;">examiner contract signed and dated</a></li>
        <li>a professional profile photo with a white background for your Path ID card.</li>
      </ul>
    </div>
    ${preassignedSessionsHtml}
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      <p style="margin:0 0 10px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">${inductionStepNumber}. CONFIRM AVAILABILITY FOR <strong><em><u>ONE</u></em></strong> INDUCTION SESSION:</p>
      ${inductionOptionsHtml}
      <div style="margin-top:14px;padding-top:14px;border-top:1px solid #d9dfdc;">
        <p style="margin:0 0 10px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">The Zoom access details for the induction session are as follows:</p>
        <p style="margin:0 0 6px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Link: <a href="${escapeEmailAttribute(zoomLink)}" style="color:#00506b;font-weight:700;">${escapeEmailHtml(zoomLink)}</a></p>
        <p style="margin:0 0 6px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Zoom ID: <strong>${escapeEmailHtml(zoomId)}</strong></p>
        <p style="margin:0;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Password: <strong>${escapeEmailHtml(zoomPassword)}</strong></p>
      </div>
    </div>
    ${certificationProgrammesHtml}
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Should you have any questions or require any further information, please let us know.</p>
    <p style="margin:0;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Welcome to Path International Examinations. We look forward to working with you!</p>
  `;
  const html = pathEmailShell({
    label: "Successful application",
    title: ACCEPTED_APPLICATION_SUBJECT,
    bodyHtml,
  });
  const text = `Successful application\n${ACCEPTED_APPLICATION_SUBJECT}\n\nDear ${fullName},\n\nWe are delighted to inform you that your application for the role of Examiner at Path International Examinations has been accepted. We are confident that you will be a valuable addition to our academic team.\n\nTo formally accept this offer and secure your place, please complete the following steps within 3 working days:\n\n1. SEND THESE FILES TO ADMIN@PATHEXAMINATIONS.COM:\n\nexaminer contract signed and dated\n${CONTRACT_LINK}\n\na professional profile photo with a white background for your Path ID card.${preassignedSessionsText}\n\n${inductionStepNumber}. CONFIRM AVAILABILITY FOR ONE INDUCTION SESSION:\n\n${inductionOptionsText}\n\nThe Zoom access details for the induction session are as follows:\n\nLink: ${zoomLink}\nZoom ID: ${zoomId}\nPassword: ${zoomPassword}${certificationProgrammesText}\n\nShould you have any questions or require any further information, please let us know.\n\nWelcome to Path International Examinations. We look forward to working with you!\n\nBest regards,\n\nPath International Examinations`;
  return { html, text };
};

const buildUnsuccessfulApplicationEmail = (button) => {
  const fullName = cleanEmailValue(button.dataset.fullName);
  if (!fullName) return { error: "Potential entry full name is required." };
  const safeName = escapeEmailHtml(fullName);
  const bodyHtml = `
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Dear ${safeName},</p>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Thank you very much for your interest in joining Path International Examinations and for taking part in our selection process.</p>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">After careful consideration, we regret to inform you that we will not be moving forward with your application at this stage. At present, we do not have active examination sessions requiring additional examiners, so we are not currently expanding our examiner team.</p>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">However, we truly appreciate your interest and the time you invested in the process. We will keep your profile in our database and may contact you in the future should new opportunities arise that match your experience and our academic needs.</p>
    <p style="margin:0;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We wish you every success in your professional journey and thank you once again for your interest in Path International Examinations.</p>
  `;
  const html = pathEmailShell({
    label: "Application update",
    title: "Update on your application",
    bodyHtml,
  });
  const text = `Dear ${fullName},\n\nThank you very much for your interest in joining Path International Examinations and for taking part in our selection process.\n\nAfter careful consideration, we regret to inform you that we will not be moving forward with your application at this stage. At present, we do not have active examination sessions requiring additional examiners, so we are not currently expanding our examiner team.\n\nHowever, we truly appreciate your interest and the time you invested in the process. We will keep your profile in our database and may contact you in the future should new opportunities arise that match your experience and our academic needs.\n\nWe wish you every success in your professional journey and thank you once again for your interest in Path International Examinations.\n\nBest regards,\n\nPath International Examinations`;
  return { html, text };
};

const enableInvitationSentAction = (button) => {
  const actionButton = button.closest(".potential-card-actions")?.querySelector("[data-invitation-sent-action]");
  if (!actionButton) return;
  actionButton.disabled = false;
  actionButton.title = "Mark interview invitation as sent.";
};

const initPotentialInvitationEmailButtons = (root = document) => {
  root.querySelectorAll("[data-copy-potential-invitation]").forEach((button) => {
    if (button.dataset.potentialInvitationInitialized === "true") return;
    button.dataset.potentialInvitationInitialized = "true";
    button.addEventListener("click", async () => {
      const payload = buildPotentialInvitationEmail(button);
      if (payload.error) {
        potentialInvitationError(button, payload.error);
        return;
      }
      const originalText = button.dataset.originalText || button.textContent;
      button.dataset.originalText = originalText;
      try {
        await copyRichTextToClipboard(payload);
        enableInvitationSentAction(button);
        button.textContent = "Interview invitation copied.";
        button.classList.add("is-copied");
        window.setTimeout(() => {
          button.textContent = originalText;
          button.classList.remove("is-copied");
        }, 1800);
      } catch (error) {
        potentialInvitationError(button, "Could not copy the invitation. Please try again.");
      }
    });
  });
};

const initPotentialOutcomeEmailButtons = (root = document) => {
  root.querySelectorAll("[data-copy-potential-outcome]").forEach((button) => {
    if (button.dataset.potentialOutcomeInitialized === "true") return;
    button.dataset.potentialOutcomeInitialized = "true";
    button.addEventListener("click", async () => {
      const outcome = cleanEmailValue(button.dataset.copyPotentialOutcome);
      const payload = outcome === "successful"
        ? buildSuccessfulApplicationEmail(button)
        : buildUnsuccessfulApplicationEmail(button);
      if (payload.error) {
        potentialInvitationError(button, payload.error);
        return;
      }
      const originalText = button.dataset.originalText || button.textContent;
      button.dataset.originalText = originalText;
      try {
        await copyRichTextToClipboard(payload);
        button.textContent = outcome === "successful"
          ? "Successful application email copied."
          : "Unsuccessful application email copied.";
        button.classList.add("is-copied");
        window.setTimeout(() => {
          button.textContent = originalText;
          button.classList.remove("is-copied");
        }, 1800);
      } catch (error) {
        potentialInvitationError(button, "Could not copy the email. Please try again.");
      }
    });
  });
};

const showEntryAcceptedEmailStatus = (button, message, isError = false) => {
  const status = button.closest("[data-entry-accepted-email-root]")?.querySelector("[data-entry-accepted-email-status]");
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("is-error", isError);
  window.setTimeout(() => {
    status.textContent = "";
    status.classList.remove("is-error");
  }, isError ? 2600 : 1900);
};

const buildEntryAcceptedApplicationEmail = (button, requireEmail = false) => {
  const root = button.closest("[data-entry-accepted-email-root]");
  const payload = buildSuccessfulApplicationEmail(root || button);
  if (payload.error) return payload;
  const email = cleanEmailValue(root?.dataset.email);
  if (requireEmail && !email) return { error: "Potential entry email is required." };
  return {
    ...payload,
    email,
    subject: ACCEPTED_APPLICATION_SUBJECT,
  };
};

const buildEntryAcceptedGmailUrl = ({ email, subject }) => (
  `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(email)}&su=${encodeURIComponent(subject)}`
);

const initEntryAcceptedEmailButtons = (root = document) => {
  root.querySelectorAll("[data-send-entry-accepted-email]").forEach((button) => {
    if (button.dataset.entryAcceptedSendInitialized === "true") return;
    button.dataset.entryAcceptedSendInitialized = "true";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const payload = buildEntryAcceptedApplicationEmail(button, true);
      if (payload.error) {
        showEntryAcceptedEmailStatus(button, payload.error, true);
        return;
      }
      let copied = false;
      try {
        await copyRichTextToClipboard(payload);
        copied = true;
      } catch (error) {
        copied = false;
      }
      window.open(buildEntryAcceptedGmailUrl(payload), "_blank", "noopener,noreferrer");
      showEntryAcceptedEmailStatus(
        button,
        copied
          ? "Application acceptance email copied. Paste it into Gmail to keep the design."
          : "Gmail opened. If the email was not copied, use the copy button and paste it manually.",
        !copied,
      );
    });
  });
  root.querySelectorAll("[data-copy-entry-accepted-email]").forEach((button) => {
    if (button.dataset.entryAcceptedCopyInitialized === "true") return;
    button.dataset.entryAcceptedCopyInitialized = "true";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const payload = buildEntryAcceptedApplicationEmail(button, false);
      if (payload.error) {
        showEntryAcceptedEmailStatus(button, payload.error, true);
        return;
      }
      try {
        await copyRichTextToClipboard(payload);
        showEntryAcceptedEmailStatus(button, "Application acceptance email copied.");
      } catch (error) {
        showEntryAcceptedEmailStatus(button, "Could not copy the email. Please try again.", true);
      }
    });
  });
};

const buildEntryAcceptedWhatsAppMessage = (button) => {
  const root = button?.closest?.("[data-entry-accepted-email-root]") || button;
  const fullName = cleanEmailValue(root?.dataset.fullName);
  const firstName = cleanEmailValue(root?.dataset.firstName) || fullName.split(/\s+/).find(Boolean) || fullName;
  if (!firstName) return { error: "Potential entry name is required." };
  const text = `Hello ${firstName}!

I hope you're doing well. 😀

I'm Brenda from Path International Examinations. It’s a pleasure to be in touch!

I'm delighted to let you know that I've just sent you an email confirming that *your application has been accepted*. Congratulations, and welcome to the Path team!

To complete the onboarding process, we'd appreciate it if you could complete the following steps *within the next three working days*:

1️⃣🅰️ Read, complete, sign, and return the contract.
1️⃣🅱️ Send us a profile photo with a white background, which will be used for your physical staff ID card.
2️⃣ Pre-confirm your participation in your assigned exam sessions.
3️⃣ Confirm your availability for one of the induction sessions.
4️⃣ Confirm your availability for the certification programmes associated with your role(s).

If you have any questions or need any assistance, please don't hesitate to get in touch—we'll be happy to help! 💙

We're excited to have you with us and look forward to working together very soon!

Kind regards,
Brenda`;
  return { text };
};

const showEntryAcceptedWhatsAppStatus = (button, message, isError = false) => {
  const status = button.closest("[data-entry-accepted-email-root]")?.querySelector("[data-entry-accepted-whatsapp-status]");
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("is-error", isError);
  window.setTimeout(() => {
    status.textContent = "";
    status.classList.remove("is-error");
  }, isError ? 2600 : 1900);
};

const initEntryAcceptedWhatsAppButtons = (root = document) => {
  root.querySelectorAll("[data-copy-entry-accepted-whatsapp]").forEach((button) => {
    if (button.dataset.entryAcceptedWhatsappCopyInitialized === "true") return;
    button.dataset.entryAcceptedWhatsappCopyInitialized = "true";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const payload = buildEntryAcceptedWhatsAppMessage(button);
      if (payload.error) {
        showEntryAcceptedWhatsAppStatus(button, payload.error, true);
        return;
      }
      try {
        await copyTextToClipboard(payload.text);
        showEntryAcceptedWhatsAppStatus(button, "WhatsApp message copied.");
      } catch (error) {
        showEntryAcceptedWhatsAppStatus(button, "Could not copy the WhatsApp message. Please try again.", true);
      }
    });
  });
};

const buildPotentialGmailUrl = (email) => (
  `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(cleanEmailValue(email))}`
);

const initPotentialGmailButtons = (root = document) => {
  root.querySelectorAll("[data-potential-gmail-email]").forEach((button) => {
    if (button.dataset.potentialGmailInitialized === "true") return;
    button.dataset.potentialGmailInitialized = "true";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const email = cleanEmailValue(button.dataset.potentialGmailEmail);
      if (!email) return;
      window.open(buildPotentialGmailUrl(email), "_blank", "noopener,noreferrer");
    });
  });
};

const roleLabelForSection = (sectionKey) => ({
  supervisor: "Supervisor",
  examiner: "Examiner",
  intern: "Intern",
}[sectionKey] || "Staff member");

const roleInvitationCopy = (role) => ({
  Supervisor: { article: "a", label: "Supervisor" },
  Examiner: { article: "an", label: "Examiner" },
  Intern: { article: "an", label: "Intern" },
}[role] || { article: "a", label: role || "staff member" });

const arrivalMinutesForRole = (role) => (role === "Examiner" ? "40" : "50");

const formatEmojiForSession = (sessionFormat) => {
  if (sessionFormat === "Onsite") return "🏫";
  if (sessionFormat === "Online" || sessionFormat === "Online at exam centre") return "💻";
  return "";
};

const formatGmailSubjectDate = (isoDate) => {
  const match = cleanEmailValue(isoDate).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return "";
  const year = Number.parseInt(match[1], 10);
  const monthIndex = Number.parseInt(match[2], 10) - 1;
  const day = Number.parseInt(match[3], 10);
  const date = new Date(year, monthIndex, day);
  const month = date.toLocaleDateString("en-US", { month: "long" });
  return `${day}${ordinalSuffix(day)} ${month}`;
};

const institutionNameFromSession = (panel) => {
  const sessionName = cleanEmailValue(panel?.dataset.sessionName);
  return sessionName || "Path exam session";
};

const buildStaffGmailUrl = ({ email, role, panel }) => {
  const subjectParts = [
    `${role.toUpperCase()} – ${cleanEmailValue(panel?.dataset.sessionFormat)}`,
    `(${formatGmailSubjectDate(panel?.dataset.sessionDate)})`,
    `- ${institutionNameFromSession(panel)}`,
  ].filter((part) => !/(^undefined$|^null$)/i.test(part));
  const subject = subjectParts.join(" ");
  return `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(email)}&su=${encodeURIComponent(subject)}`;
};

const syncStaffGmailLink = (link) => {
  const row = link.closest("[data-supervisor-row]");
  const panel = link.closest("[data-session-modal-panel]");
  const select = row?.querySelector("[data-team-member-select]");
  const option = select ? selectedTeamMemberOption(select) : null;
  const email = cleanEmailValue(option?.dataset.email || link.textContent);
  if (!email) return;
  const role = roleLabelForSection(row?.dataset.sectionKey || "");
  link.href = buildStaffGmailUrl({ email, role, panel });
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.title = "Open Gmail compose";
};

const initStaffGmailLinks = (root = document) => {
  root.querySelectorAll("[data-staff-gmail-link]").forEach((link) => {
    syncStaffGmailLink(link);
    if (link.dataset.gmailInitialized === "true") return;
    link.dataset.gmailInitialized = "true";
    link.addEventListener("click", (event) => {
      event.preventDefault();
      syncStaffGmailLink(link);
      const href = link.getAttribute("href");
      if (!href || href === "#") return;
      window.open(href, "_blank", "noopener,noreferrer");
    });
  });
};

const buildMailtoLink = ({ to, subject, body }) => {
  return `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
};

const collectInvitationTimeRanges = (row) => Array.from(row?.querySelectorAll("[data-time-range-row]") || [])
  .map((rangeRow) => {
    const inputs = Array.from(rangeRow.querySelectorAll("[data-time-input]"));
    return {
      start: cleanEmailValue(inputs[0]?.value),
      end: cleanEmailValue(inputs[1]?.value),
    };
  })
  .filter((range) => range.start && range.end)
  .sort((left, right) => left.start.localeCompare(right.start))
  .map((range) => `${range.start} – ${range.end}`);

const feeTextFromInput = (row, selector, currencySelector) => {
  const input = row?.querySelector(selector);
  const value = cleanEmailValue(input?.value);
  if (!value) return "";
  const currency = currencyFromFeeValue(value) || cleanEmailValue(row?.querySelector(currencySelector)?.value);
  const amount = value.replace(/^[A-Z]{3}\s+/i, "").trim();
  return currency && !value.toUpperCase().startsWith(`${currency.toUpperCase()} `) ? `${currency} ${amount}` : value;
};

const collectInvitationFeeLines = (row) => {
  const lines = [];
  const km = cleanEmailValue(row?.querySelector("[data-km-input]")?.value);
  if (km) lines.push({ label: "Km.", value: `${km} km` });
  [
    ["Role fee", "[data-role-fee-input]", "[data-role-fee-currency-input]"],
    ["Device dep.", "[data-device-dep-input]", "[data-device-dep-currency-input]"],
    ["Commuting", "[data-commuting-input]", "[data-commuting-currency-input]"],
    ["Fuel", "[data-fuel-input]", "[data-fuel-currency-input]"],
    ["Vehicle dep.", "[data-vehicle-input]", "[data-vehicle-currency-input]"],
    ["Seniority", "[data-seniority-input]", "[data-seniority-currency-input]"],
  ].forEach(([label, valueSelector, currencySelector]) => {
    const value = feeTextFromInput(row, valueSelector, currencySelector);
    if (value) lines.push({ label, value });
  });
  return lines;
};

const totalFeeForInvitation = (row) => (
  cleanEmailValue(row?.querySelector("[data-total-fee-value]")?.textContent)
  || cleanEmailValue(row?.querySelector("[data-total-fee-cell]")?.textContent)
  || "-"
);

const invitationStatusForParticipation = (participation) => {
  if (participation === "Confirmed") {
    return {
      label: "Confirmed",
      background: "#eef5ed",
      border: "#86aa83",
      color: "#4f7f4c",
    };
  }
  if (participation === "Pre-confirmed") {
    return {
      label: "Pre-confirmed",
      background: "#e5f6fb",
      border: "#8fd4e6",
      color: "#087896",
    };
  }
  return {
    label: participation === "Pending" ? "To be confirmed" : participation || "To be confirmed",
    background: "#FEF3C7",
    border: "#FDE68A",
    color: "#92400E",
  };
};

const collectInvitationContacts = (form, options = {}) => {
  const useSavedParticipation = Boolean(options.useSavedParticipation);
  const roles = [
    ["supervisor", "Supervisor"],
    ["examiner", "Examiner"],
    ["intern", "Intern"],
  ];
  return roles.flatMap(([sectionKey, role]) => {
    const rows = Array.from(form?.querySelectorAll(`[data-supervisor-row][data-section-key="${sectionKey}"]`) || []);
    const contacts = rows.map((row) => {
      const select = row.querySelector("[data-team-member-select]");
      const option = select ? selectedTeamMemberOption(select) : null;
      const name = cleanEmailValue(option?.dataset.name);
      if (!name) return null;
      const phone = cleanEmailValue(option?.dataset.phone);
      const participation = useSavedParticipation
        ? savedParticipationStatus(row)
        : cleanEmailValue(row.querySelector("[data-participation-select]")?.value);
      return { role, name, phone, participation };
    }).filter(Boolean);
    return contacts.map((contact, index) => ({
      label: contacts.length > 1 ? `${role} ${index + 1}` : role,
      name: contact.name,
      phone: contact.phone,
      invitationStatus: invitationStatusForParticipation(contact.participation),
    }));
  });
};

const assignedInvitationStaffRows = (form) => Array.from(form?.querySelectorAll("[data-supervisor-row]") || [])
  .filter((row) => row.querySelector("[data-team-member-select]")?.value);

const savedInvitationStaffRows = (form) => Array.from(form?.querySelectorAll("[data-supervisor-row]") || [])
  .filter((row) => cleanEmailValue(row.dataset.savedTeamMemberId));

const normalizeParticipationStatus = (status) => (
  cleanEmailValue(status) === "Sent" ? "Pre-confirmation sent" : cleanEmailValue(status)
);

const savedParticipationStatus = (row) => normalizeParticipationStatus(row?.dataset.savedParticipationStatus) || "Pending";

const hasPendingOrSentInvitationStaff = (form) => savedInvitationStaffRows(form)
  .some((row) => savedParticipationStatus(row) !== "Confirmed");

const staffingFinalEmailReady = (form) => form?.dataset.staffingFinalEmailReady === "true";

const logisticsFinalEmailReady = (form) => form?.dataset.logisticsFinalEmailReady === "true";

const formHasUnsavedStaffChanges = (form) => form?.dataset.staffChangesUnsaved === "true";

const markStaffChangesUnsaved = (form) => {
  if (!form) return;
  form.dataset.staffChangesUnsaved = "true";
  syncInvitationEmailCopyButtons(form);
};

const canCopyFinalStaffStructureEmail = (form) => (
  staffingFinalEmailReady(form) && logisticsFinalEmailReady(form) && !formHasUnsavedStaffChanges(form)
);

const invitationEmailButtonState = (button) => {
  const row = button.closest("[data-supervisor-row]");
  const form = button.closest("[data-session-members-form]");
  const hasMember = Boolean(row?.querySelector("[data-team-member-select]")?.value);
  if (formHasUnsavedStaffChanges(form)) {
    return { enabled: false, title: "Save the staff changes before copying an email." };
  }
  if (!row || !form || !hasMember) {
    return { enabled: false, title: "Select a staff member before copying the invitation email." };
  }
  if (canCopyFinalStaffStructureEmail(form)) {
    return { enabled: true, title: "Copy final staff structure email" };
  }
  if (hasPendingOrSentInvitationStaff(form)) {
    const participation = savedParticipationStatus(row);
    if (participation === "Pending") {
      return { enabled: true, title: "Copy invitation email" };
    }
    if (participation !== "Confirmed") {
      return { enabled: false, title: "Invitation email already sent" };
    }
    if (participation === "Confirmed") {
      return { enabled: false, title: "Participation already confirmed" };
    }
  }
  if (!staffingFinalEmailReady(form)) {
    return { enabled: false, title: cleanEmailValue(form.dataset.staffingEmailBlockerMessage) || "Waiting for all staff members to confirm their participation." };
  }
  if (!logisticsFinalEmailReady(form)) {
    return { enabled: false, title: cleanEmailValue(form.dataset.logisticsEmailBlockerMessage) || "Waiting for logistics confirmation" };
  }
  return { enabled: false, title: "Email copy unavailable" };
};

const syncInvitationEmailCopyButtons = (root = document) => {
  const scope = root.closest?.("[data-session-members-form]") || root;
  scope.querySelectorAll?.("[data-copy-invitation-email]").forEach((button) => {
    const state = invitationEmailButtonState(button);
    button.disabled = !state.enabled;
    button.title = state.title;
    button.setAttribute("aria-label", state.title);
    button.classList.toggle("is-disabled", !state.enabled);
    if (state.enabled) {
      delete button.dataset.rowLockDisabled;
    }
  });
};

const buildInvitationEmail = (button) => {
  const row = button.closest("[data-supervisor-row]");
  const form = button.closest("[data-session-members-form]");
  const panel = button.closest("[data-session-modal-panel]");
  const select = row?.querySelector("[data-team-member-select]");
  const option = select ? selectedTeamMemberOption(select) : null;
  const fullName = cleanEmailValue(option?.dataset.name);
  if (!row || !form || !panel || !fullName) return null;

  const sessionName = cleanEmailValue(panel.dataset.sessionName);
  const role = roleLabelForSection(row.dataset.sectionKey || "");
  const formattedDate = formatInvitationDate(panel.dataset.sessionDate);
  const timeRanges = collectInvitationTimeRanges(row);
  const sessionFormat = cleanEmailValue(panel.dataset.sessionFormat);
  const formatEmoji = formatEmojiForSession(sessionFormat);
  const address = cleanEmailValue(panel.dataset.sessionAddress);
  const detailsUrl = cleanEmailValue(panel.dataset.sessionDetailsUrl);
  const reportImageUrl = cleanEmailValue(panel.dataset.reportImageUrl);
  const feeLines = collectInvitationFeeLines(row);
  const totalFee = totalFeeForInvitation(row);
  const finalStaffStructureReady = canCopyFinalStaffStructureEmail(form);
  const contacts = collectInvitationContacts(form, { useSavedParticipation: finalStaffStructureReady });
  const logisticsEnabled = finalStaffStructureReady
    ? form.dataset.logisticsApplies === "true"
    : rowHasActiveLogisticsControl(row);
  const logisticsUrl = finalStaffStructureReady
    ? cleanEmailValue(form.dataset.logisticsFilesUrl)
    : cleanEmailValue(form.querySelector("[data-logistics-files-link]")?.getAttribute("href"));
  const recipientParticipation = savedParticipationStatus(row);
  if (!finalStaffStructureReady && recipientParticipation !== "Pending") return null;
  const roleData = roleInvitationCopy(role);
  const pathBlue = "#00506b";
  const pathCyan50 = "#e7f5f8";
  const pathBlue50 = "#e6f0f3";
  const pathGrey50 = "#f1f3f2";
  const pathYellow50 = "#fbf4e6";
  const pathAmberDark = "#8a5a00";
  const pathRed50 = "#fbecea";
  const pathRed = "#cd4d40";
  const pathBorder = "#d9dfdc";
  const pathText = "#111115";
  const pathMuted = "#62727a";
  const fontStack = "Arial, Helvetica, sans-serif";
  const bodyStyle = `margin:0;padding:0;background:${pathBlue};color:${pathText};font:400 15px/1.55 ${fontStack};`;
  const paragraphStyle = `margin:0 0 14px;color:${pathText};font:400 15px/1.55 ${fontStack};`;
  const cardCellStyle = `padding:26px 28px;background:#ffffff;border:1px solid ${pathBorder};border-radius:16px;`;
  const sectionCardStyle = `padding:22px;background:#ffffff;border:1px solid ${pathBorder};border-left:4px solid ${pathBlue};border-radius:14px;`;
  const sectionTitleStyle = `margin:0 0 8px;color:${pathBlue};font:700 18px ${fontStack};`;
  const sectionIntroStyle = `margin:0 0 16px;color:${pathMuted};font:400 14px/1.5 ${fontStack};`;
  const smallLabelStyle = `padding:0 0 4px;color:${pathMuted};font:700 11px/1.3 ${fontStack};letter-spacing:1px;text-transform:uppercase;`;
  const valueStyle = `padding:0 0 16px;color:${pathText};font:700 16px/1.45 ${fontStack};`;
  const safeName = escapeEmailHtml(fullName);
  const safeRole = escapeEmailHtml(roleData.label);
  const introductionHtml = `We’re pleased to inform you that you have been selected as ${escapeEmailHtml(roleData.article)} <strong>${safeRole}</strong> for the upcoming Path exam session, subject to your confirmation:`;
  const introductionText = `We’re pleased to inform you that you have been selected as ${roleData.article} ${roleData.label} for the upcoming Path exam session, subject to your confirmation:`;
  const invitationSenderEmail = "admin@pathexaminations.com";
  const replySubject = `Re: Path exam session invitation - ${sessionName || "Exam session"} - ${fullName}`;
  const confirmBody = "Dear Path Team,\r\n\r\n"
    + "I confirm my participation in this exam session and acknowledge that I have received the session material correctly.\r\n\r\n"
    + "Kind regards,";
  const questionBody = "Dear Path Team,\r\n\r\n"
    + "Before confirming my participation, I would like to ask the following question(s):";
  const declineBody = "Dear Path Team,\r\n\r\n"
    + "I regret to inform you that I won’t be able to participate in this exam session.\r\n\r\n"
    + "Kind regards,";
  const confirmMailto = buildMailtoLink({ to: invitationSenderEmail, subject: replySubject, body: confirmBody });
  const questionMailto = buildMailtoLink({ to: invitationSenderEmail, subject: replySubject, body: questionBody });
  const declineMailto = buildMailtoLink({ to: invitationSenderEmail, subject: replySubject, body: declineBody });
  const quickReplyButtonsHtml = `
    <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;margin:18px 0 8px 0;border-collapse:collapse;">
      <tr>
        <td style="padding-bottom:8px;">
          <a href="${escapeEmailAttribute(confirmMailto)}" style="display:inline-block;text-decoration:none;padding:9px 13px;border-radius:999px;background:#eef5ed;color:#4f7f4c;border:1px solid #86aa83;font:600 13px/1.2 ${fontStack};">Click here to confirm participation and material reception</a>
        </td>
      </tr>
      <tr>
        <td style="padding-bottom:8px;">
          <a href="${escapeEmailAttribute(questionMailto)}" style="display:inline-block;text-decoration:none;padding:9px 13px;border-radius:999px;background:${pathYellow50};color:${pathAmberDark};border:1px solid #e4c57c;font:600 13px/1.2 ${fontStack};">Click here to ask a question before confirming</a>
        </td>
      </tr>
      <tr>
        <td>
          <a href="${escapeEmailAttribute(declineMailto)}" style="display:inline-block;text-decoration:none;padding:9px 13px;border-radius:999px;background:${pathRed50};color:${pathRed};border:1px solid #e7a59f;font:600 13px/1.2 ${fontStack};">Click here to decline participation in this session</a>
        </td>
      </tr>
    </table>
  `;
  const linkedMaterialRows = emailLinkIsUsable(detailsUrl)
    ? [
      ["📅", "Exam session schedule"],
      ["🎧", "Listening and speaking exams"],
      ["📝", "Speaking marking criteria"],
    ].map(([icon, label]) => `
      <tr>
        <td style="padding:0 0 8px;">
          <a href="${escapeEmailAttribute(detailsUrl)}" style="display:block;padding:12px 14px;background:${pathGrey50};border:1px solid ${pathBorder};border-radius:10px;color:${pathText};font:700 14px/1.4 ${fontStack};text-decoration:none;">
            <span style="font-size:16px;">${icon}</span>&nbsp; ${escapeEmailHtml(label)}
            <span style="float:right;color:${pathBlue};font-weight:700;">View material →</span>
          </a>
        </td>
      </tr>
    `).join("")
    : "";
  const feeRowsHtml = feeLines.map((line) => `
    <tr>
      <td style="padding:10px 12px;border-bottom:1px solid ${pathBorder};color:${pathText};font:600 14px ${fontStack};">${escapeEmailHtml(line.label)}</td>
      <td align="right" style="padding:10px 12px;border-bottom:1px solid ${pathBorder};color:${pathText};font:700 14px ${fontStack};white-space:nowrap;">${escapeEmailHtml(line.value)}</td>
    </tr>
  `).join("");
  const contactItemsHtml = contacts.map((contact) => {
    const phone = cleanEmailValue(contact.phone);
    const status = contact.invitationStatus || invitationStatusForParticipation("");
    const telHref = phone ? `tel:${phone.replace(/[^+\d]/g, "")}` : "";
    const phoneHtml = phone
      ? `<a href="${escapeEmailAttribute(telHref)}" style="color:${pathBlue};font:600 13px ${fontStack};text-decoration:none;">${escapeEmailHtml(phone)}</a>`
      : "";
    const statusChipHtml = `<span style="display:inline-block;margin-left:8px;padding:3px 8px;border-radius:999px;border:1px solid ${status.border};background:${status.background};color:${status.color};font:600 11px/1.2 ${fontStack};vertical-align:middle;">${escapeEmailHtml(status.label)}</span>`;
    return `
      <tr>
        <td style="padding:0 0 10px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:${pathGrey50};border:1px solid ${pathBorder};border-radius:10px;">
            <tr>
              <td style="padding:12px 14px;">
                <div style="color:${pathMuted};font:700 10px/1.3 ${fontStack};letter-spacing:1px;text-transform:uppercase;">${escapeEmailHtml(contact.label)}</div>
                <div style="margin-top:3px;color:${pathText};font:700 15px/1.35 ${fontStack};">${escapeEmailHtml(contact.name)}${statusChipHtml}</div>
                ${phoneHtml ? `<div style="margin-top:3px;">${phoneHtml}</div>` : ""}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    `;
  }).join("");
  const timeHtml = timeRanges.length
    ? timeRanges.map((range) => escapeEmailHtml(range)).join(" / ")
    : "-";
  const venueHtml = sessionFormat === "Onsite" && address
    ? `
      <tr>
        <td style="${smallLabelStyle}">📍 Venue</td>
      </tr>
      <tr>
        <td style="${valueStyle};padding-bottom:0;">${escapeEmailHtml(address)}</td>
      </tr>
    `
    : "";
  const finalStructureTimeHtml = timeRanges.length
    ? timeRanges.map((range) => escapeEmailHtml(range)).join("<br>")
    : "-";
  const finalStructureTimeText = timeRanges.length ? timeRanges.join("\n") : "-";
  const finalStructureVenueText = sessionFormat === "Onsite" && address ? `\nVenue: ${address}` : "";
  if (finalStaffStructureReady) {
    const finalIntroText = logisticsEnabled
      ? "Now that the staff appointment process has been completed, all members have confirmed their participation, and the session logistics have been fully defined, we are sharing below the final staff structure for your exam session."
      : "Now that the staff appointment process has been completed and all members have confirmed their participation, we are sharing below the final staff structure for your exam session.";
    const finalLogisticsHtml = logisticsEnabled && emailLinkIsUsable(logisticsUrl)
      ? `
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:${pathCyan50};border:1px solid #b9e2ec;border-radius:14px;margin:0 0 22px;">
          <tr>
            <td style="padding:22px;">
              <h2 style="${sectionTitleStyle}">🚌✈️🚗 Travel and commuting</h2>
              <p style="${paragraphStyle};margin-bottom:0;">All logistical arrangements for your trip or commute have now been fully defined. The corresponding information and documents can be found <a href="${escapeEmailAttribute(logisticsUrl)}" style="color:${pathBlue};font-weight:700;text-decoration:underline;">in this folder</a>.</p>
            </td>
          </tr>
        </table>
      `
      : "";
    const finalLogisticsText = logisticsEnabled && emailLinkIsUsable(logisticsUrl)
      ? `\n\nTravel and commuting\n\nAll logistical arrangements for your trip or commute have now been fully defined. The corresponding information and documents can be found here:\n${logisticsUrl}`
      : "";
    const finalHtml = `<!doctype html><html><body style="${bodyStyle}">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:${pathBlue};margin:0;padding:0;">
        <tr>
          <td align="center" style="padding:24px 12px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="width:100%;max-width:680px;border-collapse:separate;border-spacing:0;">
              <tr>
                <td style="${cardCellStyle}">
                  <p style="${paragraphStyle};font-size:16px;">Dear <strong>${safeName}</strong>,</p>
                  <p style="${paragraphStyle}">Hope you’re doing very well.</p>
                  <p style="${paragraphStyle};margin-bottom:22px;">${escapeEmailHtml(finalIntroText)}</p>

                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:${pathGrey50};border:1px solid ${pathBorder};border-radius:14px;margin:0 0 20px;">
                    <tr>
                      <td style="padding:20px;">
                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                          <tr><td style="${smallLabelStyle}">🗓️ Date</td></tr>
                          <tr><td style="${valueStyle}">${escapeEmailHtml(formattedDate)}</td></tr>
                          <tr><td style="${smallLabelStyle}">🕗 Time</td></tr>
                          <tr><td style="${valueStyle}">${finalStructureTimeHtml}</td></tr>
                          <tr><td style="${smallLabelStyle}">${formatEmoji ? `${formatEmoji} ` : ""}Format</td></tr>
                          <tr><td style="${valueStyle}">${escapeEmailHtml(sessionFormat)}</td></tr>
                          ${venueHtml}
                        </table>
                      </td>
                    </tr>
                  </table>

                  ${finalLogisticsHtml}

                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;${sectionCardStyle};margin:0 0 22px;">
                    <tr><td><h2 style="${sectionTitleStyle}">👥 Staff members and emergency line</h2></td></tr>
                    <tr><td><p style="${sectionIntroStyle}">Please find below the contact details of the staff members confirmed, together with the Path emergency line for any urgent matters:</p></td></tr>
                    ${contactItemsHtml}
                    <tr>
                      <td style="padding-top:2px;">
                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:#fff4e8;border:1px solid #f1cfa8;border-radius:10px;">
                          <tr>
                            <td style="padding:12px 14px;">
                              <div style="color:#9a5a12;font:700 10px/1.3 ${fontStack};letter-spacing:1px;text-transform:uppercase;">Emergency line</div>
                              <a href="tel:+5491128508482" style="display:block;margin-top:4px;color:#9a5a12;font:800 16px/1.35 ${fontStack};text-decoration:none;">+54 9 11 2850-8482</a>
                            </td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                  </table>

                  <p style="${paragraphStyle}">Please feel free to contact us if you need anything, have any questions, or would like to check any details with us.</p>
                  <p style="${paragraphStyle};font-weight:600;">Thank you very much for your collaboration and commitment! 💙</p>
                  <p style="${paragraphStyle};margin-bottom:0;">Warm regards,</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body></html>`;

    const finalPlainContacts = contacts.map((contact) => (
      `${contact.label}: ${contact.name} (Confirmed)${contact.phone ? ` - ${contact.phone}` : ""}`
    )).join("\n");
    const finalText = `Dear ${fullName},

Hope you’re doing very well.

${finalIntroText}

Date: ${formattedDate}
Time: ${finalStructureTimeText}
${formatEmoji ? `${formatEmoji} ` : ""}Format: ${sessionFormat}${finalStructureVenueText}${finalLogisticsText}

Staff members and emergency line

Please find below the contact details of the staff members confirmed, together with the Path emergency line for any urgent matters:

${finalPlainContacts}
Emergency line: +54 9 11 2850-8482

Please feel free to contact us if you need anything, have any questions, or would like to check any details with us.

Thank you very much for your collaboration and commitment! 💙

Warm regards,`;

    return { html: finalHtml, text: finalText };
  }
  const logisticsHtml = logisticsEnabled && emailLinkIsUsable(logisticsUrl)
    ? `
      <tr>
        <td style="padding:0 0 18px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:${pathCyan50};border:1px solid #b9e2ec;border-radius:14px;">
            <tr>
              <td style="padding:22px;">
                <h2 style="${sectionTitleStyle}">🚌✈️🚗 Travel and commuting</h2>
                <p style="${paragraphStyle};margin-bottom:0;">All relevant information and documents for your trip or commute can be found <a href="${escapeEmailAttribute(logisticsUrl)}" style="color:${pathBlue};font-weight:700;text-decoration:underline;">in this folder</a>. If anything is still pending, we’ll upload it as soon as it becomes available and let you know right away. You’re also welcome to contact us at any time if there’s anything you’d like to ask or check with us.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    `
    : "";
  const materialsHtml = linkedMaterialRows
    ? `
      <tr>
        <td style="padding:0 0 18px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;${sectionCardStyle}">
            <tr><td><h2 style="${sectionTitleStyle}">🗂 Session materials</h2></td></tr>
            <tr><td><p style="${sectionIntroStyle}">Please find below:</p></td></tr>
            ${linkedMaterialRows}
          </table>
        </td>
      </tr>
    `
    : "";
  const imageHtml = emailLinkIsUsable(reportImageUrl)
    ? `<tr><td style="padding-top:14px;"><img src="${escapeEmailAttribute(reportImageUrl)}" alt="End-of-session report reference" style="display:block;width:100%;max-width:520px;height:auto;border:0;border-radius:10px;"></td></tr>`
    : "";

  const html = `<!doctype html><html><body style="${bodyStyle}">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:${pathBlue};margin:0;padding:0;">
      <tr>
        <td align="center" style="padding:24px 12px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="width:100%;max-width:680px;border-collapse:separate;border-spacing:0;">
            <tr>
              <td style="${cardCellStyle}">
                <p style="${paragraphStyle};font-size:16px;">Dear <strong>${safeName}</strong>,</p>
                <p style="${paragraphStyle}">Hope you’re doing very well.</p>
                <table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;margin:0 0 16px;">
                  <tr>
                    <td style="padding:6px 10px;background:${pathYellow50};border:1px solid #e4c57c;border-radius:999px;color:${pathAmberDark};font:700 12px ${fontStack};">⏳ Participation awaiting your confirmation</td>
                  </tr>
                </table>
                <p style="${paragraphStyle};margin-bottom:22px;">${introductionHtml}</p>

                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:${pathGrey50};border:1px solid ${pathBorder};border-radius:14px;margin:0 0 20px;">
                  <tr>
                    <td style="padding:20px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                        <tr><td style="${smallLabelStyle}">🗓️ Date</td></tr>
                        <tr><td style="${valueStyle}">${escapeEmailHtml(formattedDate)}</td></tr>
                        <tr><td style="${smallLabelStyle}">🕗 Time</td></tr>
                        <tr><td style="${valueStyle}">${timeHtml} <em style="font:400 14px/1.4 ${fontStack};color:${pathMuted};">(Please make sure to arrive at least ${arrivalMinutesForRole(role)} minutes before the session begins)</em></td></tr>
                        <tr><td style="${smallLabelStyle}">${formatEmoji ? `${formatEmoji} ` : ""}Format</td></tr>
                        <tr><td style="${valueStyle}">${escapeEmailHtml(sessionFormat)}</td></tr>
                        ${venueHtml}
                      </table>
                    </td>
                  </tr>
                </table>

                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                  <tr>
                    <td style="padding:0 0 18px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;${sectionCardStyle}">
                        <tr><td colspan="2"><h2 style="${sectionTitleStyle}">📑 Fees and invoice</h2></td></tr>
                        <tr><td colspan="2"><p style="${sectionIntroStyle}">Below you’ll find the breakdown of your exam session fee:</p></td></tr>
                        <tr>
                          <td colspan="2">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;border:1px solid ${pathBorder};border-radius:10px;overflow:hidden;">
                              <tr>
                                <td style="padding:9px 12px;background:${pathGrey50};color:${pathMuted};font:700 11px ${fontStack};letter-spacing:.8px;text-transform:uppercase;">Concept</td>
                                <td align="right" style="padding:9px 12px;background:${pathGrey50};color:${pathMuted};font:700 11px ${fontStack};letter-spacing:.8px;text-transform:uppercase;">Amount</td>
                              </tr>
                              ${feeRowsHtml}
                              <tr>
                                <td style="padding:14px 12px;background:${pathCyan50};border-top:2px solid ${pathBlue};color:${pathBlue};font:800 15px ${fontStack};">TOTAL FEE</td>
                                <td align="right" style="padding:14px 12px;background:${pathCyan50};border-top:2px solid ${pathBlue};color:${pathBlue};font:800 17px ${fontStack};white-space:nowrap;">${escapeEmailHtml(totalFee)}</td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                        <tr>
                          <td colspan="2" style="padding-top:14px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:${pathBlue50};border-radius:10px;">
                              <tr>
                                <td style="padding:12px 14px;color:${pathText};font:400 14px/1.5 ${fontStack};">Once all your exam sessions are over, please send a unified invoice with the <strong>TOTAL FEE</strong> of all sessions to <a href="mailto:finance@pathexaminations.com" style="color:${pathBlue};font-weight:700;text-decoration:underline;">finance@pathexaminations.com</a>.</td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  ${materialsHtml}
                  <tr>
                    <td style="padding:0 0 18px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;${sectionCardStyle}">
                        <tr><td><h2 style="${sectionTitleStyle}">👥 Staff members and emergency line</h2></td></tr>
                        <tr><td><p style="${sectionIntroStyle}">Below are the contact details of the staff members assigned to your exam session, as well as the Path emergency line for any urgent matters:</p></td></tr>
                        ${contactItemsHtml}
                        <tr>
                          <td style="padding-top:2px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;background:#fff4e8;border:1px solid #f1cfa8;border-radius:10px;">
                              <tr>
                                <td style="padding:12px 14px;">
                                  <div style="color:#9a5a12;font:700 10px/1.3 ${fontStack};letter-spacing:1px;text-transform:uppercase;">Emergency line</div>
                                  <a href="tel:+5491128508482" style="display:block;margin-top:4px;color:#9a5a12;font:800 16px/1.35 ${fontStack};text-decoration:none;">+54 9 11 2850-8482</a>
                                </td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  ${logisticsHtml}
                  <tr>
                    <td style="padding:0 0 18px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;${sectionCardStyle}">
                        <tr><td><h2 style="${sectionTitleStyle}">🗣 Attendance, marks and examiners’ recordings</h2></td></tr>
                        <tr><td><p style="${sectionIntroStyle}">Please make sure to:</p></td></tr>
                        ${[
                          "Complete the attendance for the Listening, Reading and Writing module on Sinapsis.",
                          "Upload all Speaking marks on Sinapsis immediately after each interview.",
                          "Verify that you and all Speaking Examiners have uploaded their Speaking marks on Sinapsis.",
                          "Upload your own recordings of the Speaking module and remind the Speaking Examiners to upload theirs within 24 working hours of the session ending.",
                        ].map((item) => `
                          <tr>
                            <td style="padding:0 0 10px;">
                              <table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                                <tr>
                                  <td valign="top" style="padding:0 9px 0 0;color:${pathBlue};font:800 15px ${fontStack};">✓</td>
                                  <td style="color:${pathText};font:400 14px/1.5 ${fontStack};">${escapeEmailHtml(item)}</td>
                                </tr>
                              </table>
                            </td>
                          </tr>
                        `).join("")}
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:0 0 22px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;${sectionCardStyle}">
                        <tr><td><h2 style="${sectionTitleStyle}">📋 End-of-session report</h2></td></tr>
                        <tr><td><p style="${paragraphStyle};margin-bottom:0;">Before leaving the venue, please make sure you’ve completed and submitted the End-of-session report in full, and that the Head of Centre has completed theirs too.</p></td></tr>
                        ${imageHtml}
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-top:4px;">
                      <p style="${paragraphStyle}">We’d appreciate it if you could confirm receipt of this email and verify that you can access all the materials mentioned above.</p>
                      ${quickReplyButtonsHtml}
                      <p style="${paragraphStyle};font-weight:600;">Thank you very much for your collaboration and commitment! 💙</p>
                      <p style="${paragraphStyle};margin-bottom:0;">Warm regards,</p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body></html>`;

  const plainFeeLines = feeLines.map((line) => `${line.label}: ${line.value}`).join("\n");
  const plainMaterials = linkedMaterialRows ? [
    `Exam session schedule: ${detailsUrl}`,
    `Listening and speaking exams: ${detailsUrl}`,
    `Speaking marking criteria: ${detailsUrl}`,
  ].join("\n") : "";
  const plainContacts = contacts.map((contact) => {
    const status = contact.invitationStatus?.label || invitationStatusForParticipation("").label;
    return `${contact.label}: ${contact.name} (${status})${contact.phone ? ` - ${contact.phone}` : ""}`;
  }).join("\n");
  const plainVenue = sessionFormat === "Onsite" && address ? `\n📍 Venue: ${address}` : "";
  const plainLogistics = logisticsEnabled && emailLinkIsUsable(logisticsUrl)
    ? `\n\n🚌✈️🚗 Travel and commuting\n\nAll relevant information and documents for your trip or commute can be found in this folder: ${logisticsUrl}. If anything is still pending, we’ll upload it as soon as it becomes available and let you know right away. You’re also welcome to contact us at any time if there’s anything you’d like to ask or check with us.`
    : "";
  const text = `Dear ${fullName},

Hope you’re doing very well.

${introductionText}

🗓️ Date: ${formattedDate}
🕗 Time: ${timeRanges.join(" / ") || "-"} (Please make sure to arrive at least ${arrivalMinutesForRole(role)} minutes before the session begins)

${formatEmoji ? `${formatEmoji} ` : ""}Format: ${sessionFormat}${plainVenue}

📑 Fees and invoice

Below you’ll find the breakdown of your exam session fee:

${plainFeeLines ? `${plainFeeLines}\n\n` : ""}TOTAL FEE: ${totalFee}

Once all your exam sessions are over, please send a unified invoice with the TOTAL FEE of all sessions to finance@pathexaminations.com.
${plainMaterials ? `\n\n🗂 Session materials\n\nPlease find below:\n\n${plainMaterials}` : ""}

👥 Staff members and emergency line

Below are the contact details of the staff members assigned to your exam session, as well as the Path emergency line for any urgent matters:

${plainContacts}
Emergency line: +54 9 11 2850-8482${plainLogistics}

🗣 Attendance, marks and examiners’ recordings

Please make sure to:

* Complete the attendance for the Listening, Reading and Writing module on Sinapsis.
* Upload all Speaking marks on Sinapsis immediately after each interview.
* Verify that you and all Speaking Examiners have uploaded their Speaking marks on Sinapsis.
* Upload your own recordings of the Speaking module and remind the Speaking Examiners to upload theirs within 24 working hours of the session ending.

📋 End-of-session report

Before leaving the venue, please make sure you’ve completed and submitted the End-of-session report in full, and that the Head of Centre has completed theirs too.

We’d appreciate it if you could confirm receipt of this email and verify that you can access all the materials mentioned above.

Click here to confirm participation and material reception:
${confirmMailto}

Click here to ask a question before confirming:
${questionMailto}

Click here to decline participation in this session:
${declineMailto}

Thank you very much for your collaboration and commitment! 💙

Warm regards,`;

  return { html, text };
};

const OFFICIAL_CONFIRMATION_MATERIAL_URL = "https://drive.google.com/file/d/1FfzKcWq8pED3qv5yuzx2L9n_VEx0ZysM/view?usp=drive_link";

const parseStaffOfficialConfirmationPayload = (button) => {
  try {
    const payload = JSON.parse(button?.dataset?.staffOfficialConfirmationEmailPayload || "{}");
    return payload && typeof payload === "object" ? payload : {};
  } catch (error) {
    return {};
  }
};

const officialArrivalMinutesForRole = (role) => (role === "Supervisor" ? "50" : "30");

const officialDateLabel = (isoDate) => formatInvitationDate(isoDate);

const officialTimeLabel = (value) => cleanEmailValue(value).replace(":", ".");

const collectOfficialTimeRanges = (row) => Array.from(row?.querySelectorAll("[data-time-range-row]") || [])
  .map((rangeRow) => {
    const inputs = Array.from(rangeRow.querySelectorAll("[data-time-input]"));
    const start = cleanEmailValue(inputs[0]?.value);
    const end = cleanEmailValue(inputs[1]?.value);
    return start && end ? `${officialTimeLabel(start)} to ${officialTimeLabel(end)} h` : "";
  })
  .filter(Boolean);

const officialFeeLineFromInput = (row, label, selector, currencySelector) => {
  const value = feeTextFromInput(row, selector, currencySelector);
  const amount = parseFeeValue(value);
  if (!value || amount === null || amount === 0) return null;
  return { label, value };
};

const collectOfficialFeeLines = (row) => ([
  ["Role fee", "[data-role-fee-input]", "[data-role-fee-currency-input]"],
  ["Device depreciation", "[data-device-dep-input]", "[data-device-dep-currency-input]"],
  ["Commuting", "[data-commuting-input]", "[data-commuting-currency-input]"],
  ["Fuel", "[data-fuel-input]", "[data-fuel-currency-input]"],
  ["Vehicle depreciation", "[data-vehicle-input]", "[data-vehicle-currency-input]"],
  ["Seniority", "[data-seniority-input]", "[data-seniority-currency-input]"],
]).map(([label, valueSelector, currencySelector]) => (
  officialFeeLineFromInput(row, label, valueSelector, currencySelector)
)).filter(Boolean);

const collectOfficialSessionStaff = (form) => ([
  ["supervisor", "Supervisor"],
  ["examiner", "Examiner"],
  ["intern", "Intern"],
]).flatMap(([sectionKey, role]) => {
  const rows = Array.from(form?.querySelectorAll(`[data-supervisor-row][data-section-key="${sectionKey}"]`) || []);
  return rows.map((row, index) => {
    const select = row.querySelector("[data-team-member-select]");
    const option = select ? selectedTeamMemberOption(select) : null;
    const name = cleanEmailValue(option?.dataset.name);
    const title = cleanEmailValue(option?.dataset.title);
    const participation = normalizeParticipationStatus(row.querySelector("[data-participation-select]")?.value);
    const isConfirmed = participation === "Confirmed";
    return {
      label: rows.length > 1 ? `${role} ${index + 1}` : role,
      role,
      assigned: Boolean(name),
      name,
      title,
      displayName: [title, name].filter(Boolean).join(" "),
      phone: cleanEmailValue(option?.dataset.phone) || "Phone number not available",
      dietaryRequirements: cleanEmailValue(option?.dataset.dietaryRequirements),
      seniority: option?.dataset.seniority === "true",
      status: isConfirmed ? "Confirmed" : "To be confirmed",
      statusTone: isConfirmed ? "green" : "yellow",
      emptyMessage: `This ${role.toLowerCase()} has not been assigned yet`,
    };
  });
});

const getStaffOfficialConfirmationEmailPayload = (button) => {
  const explicitPayload = parseStaffOfficialConfirmationPayload(button);
  if (Object.keys(explicitPayload).length) return explicitPayload;
  const row = button?.closest?.("[data-supervisor-row]");
  const form = button?.closest?.("[data-session-members-form]");
  const panel = button?.closest?.("[data-session-modal-panel]");
  const select = row?.querySelector?.("[data-team-member-select]");
  const option = select ? selectedTeamMemberOption(select) : null;
  const logisticsUrl = cleanEmailValue(form?.dataset?.logisticsFilesUrl)
    || cleanEmailValue(form?.querySelector?.("[data-logistics-files-link]")?.getAttribute("href"))
    || cleanEmailValue(form?.querySelector?.("[data-logistics-files-url]")?.value);
  return {
    full_name: cleanEmailValue(option?.dataset?.name) || cleanEmailValue(row?.querySelector?.("[data-staff-card-title]")?.textContent),
    role: roleLabelForSection(row?.dataset?.sectionKey || ""),
    session_name: cleanEmailValue(panel?.dataset?.sessionName),
    session_date: officialDateLabel(panel?.dataset?.sessionDate),
    time_ranges: collectOfficialTimeRanges(row),
    format: cleanEmailValue(panel?.dataset?.sessionFormat),
    address: cleanEmailValue(panel?.dataset?.sessionAddress),
    fee_lines: collectOfficialFeeLines(row),
	    total_fee: cleanEmailValue(row?.querySelector?.("[data-total-fee-value]")?.textContent),
	    logistics_status: cleanEmailValue(row?.querySelector?.("[data-logistics-control]")?.value),
	    logistics_url: logisticsUrl,
	    next_payment_date: cleanEmailValue(panel?.dataset?.staffPaymentNextPaymentDate),
	    contacts: collectOfficialSessionStaff(form),
	  };
	};

const validateStaffOfficialConfirmationEmailPayload = (payload) => {
  if (!cleanEmailValue(payload?.full_name || payload?.fullName)) return "Staff member full name is required.";
  if (cleanEmailValue(payload?.format) !== "Onsite") return "Official confirmation email is only available for onsite sessions.";
  if (!cleanEmailValue(payload?.role) || !cleanEmailValue(payload?.session_name || payload?.sessionName) || !cleanEmailValue(payload?.session_date || payload?.sessionDate)) {
    return "Exam session information is incomplete.";
  }
  if (!Array.isArray(payload?.time_ranges || payload?.timeRanges) || !(payload.time_ranges || payload.timeRanges).length) {
    return "Staff member time range is required for official confirmation emails.";
  }
  if (!cleanEmailValue(payload?.address)) return "Exam session address is required for onsite sessions.";
  const totalFee = cleanEmailValue(payload?.total_fee || payload?.totalFee);
  if (!totalFee || totalFee === "-" || totalFee.toLowerCase().includes("total fee -")) {
    return "Total fee is required for official confirmation emails.";
  }
  const logisticsStatus = cleanEmailValue(payload?.logistics_status || payload?.logisticsStatus);
  if (!["Does not apply", "Uber", "Simple logistics", "Complex logistics"].includes(logisticsStatus)) {
    return "Logistics status is required for official confirmation emails.";
  }
  if (["Uber", "Simple logistics"].includes(logisticsStatus) && !emailLinkIsUsable(payload?.logistics_url || payload?.logisticsUrl)) {
    return "Logistics folder link is required for Uber.";
  }
	  if (logisticsStatus === "Complex logistics" && !emailLinkIsUsable(payload?.logistics_url || payload?.logisticsUrl)) {
	    return "Logistics folder link is required for complex logistics.";
	  }
	  if (!cleanEmailValue(payload?.next_payment_date || payload?.nextPaymentDate)) {
	    return "Next payment date is required for official confirmation emails.";
	  }
	  return "";
	};

const officialConfirmationStatusStyle = (tone) => {
  if (tone === "green") return { background: "#eef5ed", border: "#86aa83", color: "#4f7f4c" };
  if (tone === "blue") return { background: "#e7f5f8", border: "#8fd4e6", color: "#087896" };
  if (tone === "red") return { background: "#fbecea", border: "#e7a59f", color: "#cd4d40" };
  return { background: "#fff3c4", border: "#f3d67a", color: "#8a5a00" };
};

const officialContactDisplayName = (contact) => (
  cleanEmailValue(contact.displayName)
  || [cleanEmailValue(contact.title), cleanEmailValue(contact.name)].filter(Boolean).join(" ")
  || cleanEmailValue(contact.name)
);

const officialContactWhatsAppUrl = (phone) => {
  const digits = cleanEmailValue(phone).replace(/\D/g, "");
  return digits ? `https://wa.me/${digits}` : "";
};

const officialMaterialRows = (role) => {
  if (role === "Examiner") {
    return [
      ["🗓️ Exam session schedule", "Please access this section in advance to check your assigned exam rooms and ensure your schedule information is complete. You may have been assigned to the Listening and speaking module, the Reading and writing module, or both. To verify this, compare the start and end times in this email with those shown in the PDFs. Please also review the session timings, rooms and layout in advance."],
      ["🎧🗣️ Listening and speaking module", "This section contains the materials needed to conduct the Listening and speaking module. Please access Sinapsis in advance to check that the required audio files are available and working properly before the exam session."],
      ["✅ Examiner guidelines", "Please read the examiner instructions carefully and in advance to ensure that all required procedures and protocols are followed in line with Path Examinations’ quality policies."],
    ];
  }
	  if (role === "Supervisor") {
	    return [
	      ["🗓️ Exam session schedule", "Please access this folder in advance to understand the exam session you will be supervising, including timings, exam room layout, and the start and end times of each module. A careful review is required to ensure the session runs smoothly and to identify any details that may need attention beforehand."],
	      ["📦🚚 Exam box shipment", "Once you confirm your participation as a Supervisor, our Logistics team will contact you in due course to arrange the delivery of the materials for your assigned exam session(s). You will also receive instructions on how to handle the materials after the exam session has ended."],
	      ["🎧🗣️ Material for examiners", "This folder contains the Listening and speaking module examiner guidelines and Listening audio files as back-up material. Examiners must access the official materials through Sinapsis, but these files are provided as a contingency resource in case of power or internet issues during the exam session."],
      ["✅ Supervisor guidelines", "Please read these guidelines carefully to fully understand your responsibilities during the exam session. This will help you respond appropriately at each stage or in case of unexpected situations, while ensuring compliance with Path Examinations’ quality policies and procedures."],
    ];
  }
  return [];
};

const officialConfirmationMaterialsHtml = (role, styles) => {
  const rows = officialMaterialRows(role);
  if (!rows.length) return "";
  return `
    <div style="${styles.section}">
      <h2 style="${styles.sectionTitle}">SESSION MATERIALS</h2>
      <p style="${styles.paragraph}">Please find below:</p>
      ${rows.map(([label, description]) => `
        <div style="margin:0 0 10px;padding:12px 14px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:10px;">
          <p style="margin:0 0 5px;color:#111115;font:700 14px/1.4 Arial, Helvetica, sans-serif;">${escapeEmailHtml(label)} <a href="${escapeEmailAttribute(OFFICIAL_CONFIRMATION_MATERIAL_URL)}" style="float:right;color:#00506b;font-weight:700;text-decoration:none;">View material →</a></p>
          <p style="margin:0;color:#62727a;font:italic 12px/1.45 Arial, Helvetica, sans-serif;">${escapeEmailHtml(description)}</p>
        </div>
      `).join("")}
    </div>
  `;
};

const officialConfirmationMaterialsText = (role) => {
  const rows = officialMaterialRows(role);
  if (!rows.length) return "";
  return `SESSION MATERIALS\n\nPlease find below:\n\n${rows.map(([label, description]) => `${label}\nView material: ${OFFICIAL_CONFIRMATION_MATERIAL_URL}\n${description}`).join("\n\n")}`;
};

const officialContactsHtml = (contacts, recipientRole, styles) => `
  <div style="${styles.section}">
    <h2 style="${styles.sectionTitle}">STAFF MEMBERS AND EMERGENCY LINES</h2>
    <p style="${styles.paragraph}">Below are the contact details of the staff members assigned to this exam session, as well as the Path emergency lines for any urgent matters:</p>
    ${contacts.map((contact) => {
      if (!contact.assigned) {
        const red = officialConfirmationStatusStyle("red");
        return `<div style="margin:0 0 9px;padding:12px 14px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:10px;"><p style="margin:0 0 6px;color:#62727a;font:700 11px Arial, Helvetica, sans-serif;text-transform:uppercase;">${escapeEmailHtml(contact.label)}</p><span style="display:inline-block;padding:4px 9px;border-radius:999px;background:${red.background};border:1px solid ${red.border};color:${red.color};font:700 12px Arial, Helvetica, sans-serif;">${escapeEmailHtml(contact.emptyMessage)}</span></div>`;
      }
      const tone = officialConfirmationStatusStyle(contact.statusTone);
      const dietaryRequirements = cleanEmailValue(contact.dietaryRequirements || contact.dietary_requirements);
      const dietaryTone = officialConfirmationStatusStyle("blue");
      const seniorTone = officialConfirmationStatusStyle("green");
      const seniorChip = contact.seniority || contact.isSenior ? ` <span style="display:inline-block;margin-left:6px;padding:3px 8px;border-radius:999px;background:${seniorTone.background};border:1px solid ${seniorTone.border};color:${seniorTone.color};font:700 11px Arial, Helvetica, sans-serif;">Senior</span>` : "";
      const dietaryChip = dietaryRequirements ? ` <span style="display:inline-block;margin-left:6px;padding:3px 8px;border-radius:999px;background:${dietaryTone.background};border:1px solid ${dietaryTone.border};color:${dietaryTone.color};font:700 11px Arial, Helvetica, sans-serif;">${escapeEmailHtml(dietaryRequirements)}</span>` : "";
      const phoneText = cleanEmailValue(contact.phone) || "Phone number not available";
      const phoneUrl = officialContactWhatsAppUrl(phoneText);
      const phoneHtml = phoneUrl
        ? `<a href="${escapeEmailAttribute(phoneUrl)}" style="color:#00506b;font:600 13px Arial, Helvetica, sans-serif;text-decoration:underline;">${escapeEmailHtml(phoneText)}</a>`
        : escapeEmailHtml(phoneText);
      return `<div style="margin:0 0 9px;padding:12px 14px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:10px;"><p style="margin:0 0 4px;color:#62727a;font:700 11px Arial, Helvetica, sans-serif;text-transform:uppercase;">${escapeEmailHtml(contact.label)}</p><p style="margin:0;color:#111115;font:700 15px/1.35 Arial, Helvetica, sans-serif;">${escapeEmailHtml(officialContactDisplayName(contact))}${seniorChip} <span style="display:inline-block;margin-left:6px;padding:3px 8px;border-radius:999px;background:${tone.background};border:1px solid ${tone.border};color:${tone.color};font:700 11px Arial, Helvetica, sans-serif;">${escapeEmailHtml(contact.status)}</span>${dietaryChip}</p><p style="margin:3px 0 0;color:#00506b;font:600 13px Arial, Helvetica, sans-serif;">${phoneHtml}</p></div>`;
    }).join("")}
    <div style="margin-top:12px;padding:14px 16px;background:#fff4e8;border:1px solid #f1cfa8;border-radius:10px;">
      <p style="margin:0 0 8px;color:#9a5a12;font:800 13px Arial, Helvetica, sans-serif;">Emergency lines</p>
      ${["Examiner", "Intern"].includes(recipientRole) ? `<p style="margin:0 0 8px;color:#111115;font:400 13px/1.45 Arial, Helvetica, sans-serif;">Please contact your Supervisor first before using these emergency lines.</p>` : ""}
      <p style="margin:0 0 5px;color:#111115;font:700 13px/1.45 Arial, Helvetica, sans-serif;">On business days from 9am to 3pm, contact:</p>
      <ul style="margin:0 0 10px;padding-left:20px;color:#111115;font:400 13px/1.45 Arial, Helvetica, sans-serif;">
        <li>Path Examinations office at <a href="https://wa.me/5491150954847" style="color:#00506b;font-weight:700;text-decoration:underline;">+5491150954847</a></li>
      </ul>
      <p style="margin:0 0 5px;color:#111115;font:700 13px/1.45 Arial, Helvetica, sans-serif;">Outside of business time, contact:</p>
      <ul style="margin:0;padding-left:20px;color:#111115;font:400 13px/1.45 Arial, Helvetica, sans-serif;">
        <li>Brenda Sartori at <a href="https://wa.me/5491133945761" style="color:#00506b;font-weight:700;text-decoration:underline;">+5491133945761</a></li>
        <li>Agustina Savini at <a href="https://wa.me/5491155692629" style="color:#00506b;font-weight:700;text-decoration:underline;">+5491155692629</a></li>
        <li>Pablo Demarchi at <a href="https://wa.me/5491128508482" style="color:#00506b;font-weight:700;text-decoration:underline;">+5491128508482</a></li>
      </ul>
    </div>
  </div>
`;

const officialContactsText = (contacts, recipientRole) => (
  "STAFF MEMBERS AND EMERGENCY LINES\n\n"
  + "Below are the contact details of the staff members assigned to this exam session, as well as the Path emergency lines for any urgent matters:\n\n"
  + contacts.map((contact) => (
    contact.assigned
      ? `${contact.label}\n${officialContactDisplayName(contact)}${contact.seniority || contact.isSenior ? " (Senior)" : ""} (${contact.status})${cleanEmailValue(contact.dietaryRequirements || contact.dietary_requirements) ? ` - Dietary requirements: ${cleanEmailValue(contact.dietaryRequirements || contact.dietary_requirements)}` : ""}\n${contact.phone || "Phone number not available"}${officialContactWhatsAppUrl(contact.phone) ? ` (${officialContactWhatsAppUrl(contact.phone)})` : ""}`
      : `${contact.label}\n${contact.emptyMessage}`
  )).join("\n\n")
  + `\n\nEmergency lines\n${["Examiner", "Intern"].includes(recipientRole) ? "Please contact your Supervisor first before using these emergency lines.\n" : ""}On business days from 9am to 3pm, contact:\n- Path Examinations office at +5491150954847 (https://wa.me/5491150954847)\n\nOutside of business time, contact:\n- Brenda Sartori at +5491133945761 (https://wa.me/5491133945761)\n- Agustina Savini at +5491155692629 (https://wa.me/5491155692629)\n- Pablo Demarchi at +5491128508482 (https://wa.me/5491128508482)`
);

const officialTravelCopy = (role, status, logisticsUrl) => {
  const arrival = officialArrivalMinutesForRole(role);
  if (status === "Does not apply") {
    const suffix = role === "Supervisor"
      ? `arrive ${arrival} minutes before the start of the exam session.`
      : `arrive ${arrival} minutes before the start of your first assigned module.`;
    return {
      html: `You may travel to and from the exam centre using your own vehicle or public transport. Please plan your journey accordingly, allow sufficient travel time and ${suffix}`,
      text: `You may travel to and from the exam centre using your own vehicle or public transport. Please plan your journey accordingly, allow sufficient travel time and ${suffix}`,
    };
  }
  if (["Uber", "Simple logistics"].includes(status)) {
    const suffix = role === "Supervisor"
      ? `allow sufficient travel time, and arrive ${arrival} minutes before the start of the exam session.`
      : `allow sufficient travel time and arrive ${arrival} minutes before the start of your first assigned module.`;
    const text = `You may travel to and from the exam centre using a travel app, such as Uber or Cabify. Please plan your journey accordingly, ${suffix} Once the exam session is over, please access this folder and upload your travel receipts to the folder under your name. Do not include these expenses in your final invoice.`;
    return {
      html: `You may travel to and from the exam centre using a travel app, such as Uber or Cabify. Please plan your journey accordingly, ${suffix} Once the exam session is over, please access <a href="${escapeEmailAttribute(logisticsUrl)}" style="color:#00506b;font-weight:700;text-decoration:underline;">this folder</a> and upload your travel receipts to the folder under your name. Do not include these expenses in your final invoice.`,
      text: `${text}\n${logisticsUrl}`,
    };
  }
  const first = `All relevant information and documents for your trip or commute can be found in this folder. If anything is still pending, we will upload it as soon as it becomes available and let you know right away. You are also welcome to contact us at any time if there’s anything you’d like to ask or check with us.`;
  const second = "After the exam session, if you have covered any additional expenses previously agreed or confirmed by Path Examinations, please upload the receipts to the folder under your name. Please note that expenses not previously agreed with Path Examinations, or without a corresponding receipt issued under the company’s name, cannot be reimbursed. Do not include these expenses in your final invoice.";
  return {
    html: `All relevant information and documents for your trip or commute can be found in <a href="${escapeEmailAttribute(logisticsUrl)}" style="color:#00506b;font-weight:700;text-decoration:underline;">this folder</a>. If anything is still pending, we will upload it as soon as it becomes available and let you know right away. You are also welcome to contact us at any time if there’s anything you’d like to ask or check with us.<br><br>${escapeEmailHtml(second)}`,
    text: `${first}\n${logisticsUrl}\n\n${second}`,
  };
};

const officialFinalInstructions = (role) => {
  if (role === "Examiner") {
    return {
      title: "ATTENDANCE, MARKS AND RECORDINGS",
      items: [
        "complete attendance in Sinapsis for the modules you have been assigned to.",
        "mark candidates’ speaking performance on the paper exam records after each interview.",
        "upload the recordings of the Listening and speaking module within 24 working hours after the session ends.",
      ],
    };
  }
  if (role === "Supervisor") {
    return {
      title: "EXAM SESSION FINAL CHECKS",
      items: [
        "verify that all examiners have completed candidate attendance in Sinapsis and that no candidates remain with Pending status.",
        "check with examiners that all paper candidate exam records have been marked, including those for absent candidates.",
        "remind examiners to upload the recordings of the Listening and speaking module within 24 working hours after the session ends.",
        "take an institutional picture with the Path staff and/or the Head(s) of centre.",
        "complete the End-of-session report before leaving the exam session premises.",
      ],
    };
  }
  return null;
};

const buildStaffOfficialConfirmationEmail = (button) => {
  const payload = getStaffOfficialConfirmationEmailPayload(button);
  const validationError = validateStaffOfficialConfirmationEmailPayload(payload);
  if (validationError) return { error: validationError };
  const fullName = cleanEmailValue(payload.full_name || payload.fullName);
  const role = cleanEmailValue(payload.role);
  const sessionName = cleanEmailValue(payload.session_name || payload.sessionName);
  const sessionDate = cleanEmailValue(payload.session_date || payload.sessionDate);
  const timeRanges = payload.time_ranges || payload.timeRanges || [];
  const timeLabel = timeRanges.join(" / ");
  const address = cleanEmailValue(payload.address);
  const totalFee = cleanEmailValue(payload.total_fee || payload.totalFee);
  const feeLines = Array.isArray(payload.fee_lines || payload.feeLines) ? (payload.fee_lines || payload.feeLines) : [];
	  const logisticsStatus = cleanEmailValue(payload.logistics_status || payload.logisticsStatus);
	  const logisticsUrl = cleanEmailValue(payload.logistics_url || payload.logisticsUrl);
	  const nextPaymentDate = cleanEmailValue(payload.next_payment_date || payload.nextPaymentDate);
	  const contacts = Array.isArray(payload.contacts) ? payload.contacts : [];
  const roleData = roleInvitationCopy(role);
  const arrival = officialArrivalMinutesForRole(role);
  const travel = officialTravelCopy(role, logisticsStatus, logisticsUrl);
  const finalInstructions = officialFinalInstructions(role);
  const styles = {
    paragraph: "margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;",
    section: "margin:0 0 18px;padding:16px 18px;background:#ffffff;border:1px solid #d9dfdc;border-left:4px solid #00506b;border-radius:12px;",
    sectionTitle: "margin:0 0 12px;color:#00506b;font:800 15px/1.35 Arial, Helvetica, sans-serif;letter-spacing:.4px;text-transform:uppercase;",
  };
  const invitationSenderEmail = "admin@pathexaminations.com";
  const replySubject = `Re: Path exam session invitation - ${sessionName || "Exam session"} - ${fullName}`;
  const confirmMailto = buildMailtoLink({ to: invitationSenderEmail, subject: replySubject, body: "Dear Path Team,\r\n\r\nI confirm my participation in this exam session and acknowledge that I have received the session material correctly.\r\n\r\nKind regards," });
  const questionMailto = buildMailtoLink({ to: invitationSenderEmail, subject: replySubject, body: "Dear Path Team,\r\n\r\nBefore confirming my participation, I would like to ask the following question(s):" });
  const declineMailto = buildMailtoLink({ to: invitationSenderEmail, subject: replySubject, body: "Dear Path Team,\r\n\r\nI regret to inform you that I won’t be able to participate in this exam session.\r\n\r\nKind regards," });
  const feeRowsHtml = feeLines.map((line) => `
    <tr><td style="padding:9px 12px;border-bottom:1px solid #d9dfdc;color:#111115;font:600 14px Arial, Helvetica, sans-serif;">${escapeEmailHtml(line.label)}</td><td align="right" style="padding:9px 12px;border-bottom:1px solid #d9dfdc;color:#111115;font:700 14px Arial, Helvetica, sans-serif;">${escapeEmailHtml(line.value)}</td></tr>
  `).join("");
  const materialsText = officialConfirmationMaterialsText(role);
  const finalInstructionsHtml = finalInstructions ? `
    <div style="${styles.section}">
      <h2 style="${styles.sectionTitle}">${escapeEmailHtml(finalInstructions.title)}</h2>
      <p style="${styles.paragraph}"><strong>Please make sure to:</strong></p>
      ${finalInstructions.items.map((item) => `<p style="margin:0 0 8px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">✓ ${escapeEmailHtml(item)}</p>`).join("")}
    </div>
  ` : "";
  const finalInstructionsText = finalInstructions
    ? `${finalInstructions.title}\n\nPlease make sure to:\n\n${finalInstructions.items.map((item) => `✓ ${item}`).join("\n")}`
    : "";
  const actionTagsHtml = `
    <p style="${styles.paragraph}">We’d appreciate it if you could confirm receipt of this email and verify that you can access all the materials mentioned above.</p>
    <p style="margin:0 0 8px;"><a href="${escapeEmailAttribute(confirmMailto)}" style="display:inline-block;padding:9px 13px;border-radius:999px;background:#eef5ed;color:#4f7f4c;border:1px solid #86aa83;font:700 13px Arial, Helvetica, sans-serif;text-decoration:none;">Click here to confirm participation and material reception</a></p>
    <p style="margin:0 0 8px;"><a href="${escapeEmailAttribute(questionMailto)}" style="display:inline-block;padding:9px 13px;border-radius:999px;background:#fff3c4;color:#8a5a00;border:1px solid #f3d67a;font:700 13px Arial, Helvetica, sans-serif;text-decoration:none;">Click here to ask a question before confirming</a></p>
    <p style="margin:0 0 16px;"><a href="${escapeEmailAttribute(declineMailto)}" style="display:inline-block;padding:9px 13px;border-radius:999px;background:#fbecea;color:#cd4d40;border:1px solid #e7a59f;font:700 13px Arial, Helvetica, sans-serif;text-decoration:none;">Click here to decline participation in this session</a></p>
  `;
  const bodyHtml = `
    <div style="margin:0;padding:24px;background:#00506b;font-family:Arial, Helvetica, sans-serif;color:#111115;">
      <div style="max-width:680px;margin:0 auto;background:#ffffff;border:1px solid #d9dfdc;border-radius:16px;padding:26px 28px;">
        <p style="display:inline-block;margin:0 0 14px;padding:5px 10px;border-radius:999px;background:#e7f5f8;color:#00506b;font:700 11px Arial, Helvetica, sans-serif;letter-spacing:.5px;text-transform:uppercase;">OFFICIAL CONFIRMATION</p>
        <h1 style="margin:0 0 18px;color:#00506b;font:700 24px/1.25 Arial, Helvetica, sans-serif;">Path exam session official confirmation</h1>
        <p style="${styles.paragraph}">Dear ${escapeEmailHtml(fullName)},</p>
        <p style="${styles.paragraph}">Hope you’re doing very well.</p>
        <p style="display:inline-block;margin:0 0 16px;padding:6px 11px;border-radius:999px;background:#fff3c4;color:#8a5a00;font:700 12px Arial, Helvetica, sans-serif;">⏳ Participation awaiting your confirmation</p>
        <p style="${styles.paragraph}">We’re pleased to inform you that you have been selected as ${escapeEmailHtml(roleData.article)} <strong>${escapeEmailHtml(role)}</strong> for the upcoming Path exam session, subject to your confirmation.</p>
        <div style="${styles.section}">
          <h2 style="${styles.sectionTitle}">EXAM SESSION INFORMATION</h2>
          <p style="margin:0 0 4px;color:#62727a;font:800 12px Arial, Helvetica, sans-serif;">🗓️ Date</p>
          <p style="margin:0 0 12px;color:#111115;font:700 16px Arial, Helvetica, sans-serif;">${escapeEmailHtml(sessionDate)}</p>
          <p style="margin:0 0 4px;color:#62727a;font:800 12px Arial, Helvetica, sans-serif;">🕗 Time</p>
          <p style="margin:0 0 12px;color:#111115;font:700 16px Arial, Helvetica, sans-serif;">${escapeEmailHtml(timeLabel)} GMT-3 <em style="color:#62727a;font:italic 13px/1.4 Arial, Helvetica, sans-serif;">(Please make sure to arrive at least ${arrival} minutes before the session begins)</em></p>
          <p style="margin:0 0 4px;color:#62727a;font:800 12px Arial, Helvetica, sans-serif;">💻 Format</p>
          <p style="margin:0 0 12px;color:#111115;font:700 16px Arial, Helvetica, sans-serif;">Onsite</p>
          <p style="margin:0 0 4px;color:#62727a;font:800 12px Arial, Helvetica, sans-serif;">📍 Venue</p>
          <p style="margin:0;color:#111115;font:700 16px Arial, Helvetica, sans-serif;">${escapeEmailHtml(address)}</p>
        </div>
        <div style="${styles.section}">
          <h2 style="${styles.sectionTitle}">FEES AND INVOICE</h2>
          <p style="${styles.paragraph}">Below you’ll find the breakdown of your exam session fee:</p>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;border:1px solid #d9dfdc;border-radius:10px;overflow:hidden;margin:0 0 14px;">${feeRowsHtml}<tr><td style="padding:12px;background:#e7f5f8;color:#00506b;font:800 15px Arial, Helvetica, sans-serif;">TOTAL FEE:</td><td align="right" style="padding:12px;background:#e7f5f8;color:#00506b;font:800 15px Arial, Helvetica, sans-serif;">${escapeEmailHtml(totalFee)}</td></tr></table>
	          <div style="margin:0;padding:13px 15px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:10px;">
	            <p style="margin:0 0 10px;color:#111115;font:400 13px/1.5 Arial, Helvetica, sans-serif;"><em><u>Once all your exam sessions are over</u></em>, please send one consolidated invoice to <a href="mailto:finance@pathexaminations.com" style="color:#00506b;font-weight:700;text-decoration:underline;"><strong><u>finance@pathexaminations.com</u></strong></a>, including only the <strong>sum of the total fees</strong> for all your sessions. Do not include additional expenses, as only invoices matching the system amount will be processed. The invoice may be issued in your name or someone else’s name. Please follow the <a href="https://drive.google.com/drive/u/0/my-drive" style="color:#00506b;font-weight:700;text-decoration:underline;"><strong>attached sample</strong></a> with the required company details.</p>
	            <p style="margin:0;color:#111115;font:400 13px/1.5 Arial, Helvetica, sans-serif;">Payments will be processed on <strong>${escapeEmailHtml(nextPaymentDate)}</strong> <strong>at 5:00 pm (GMT-3)</strong> and will appear as Bellis Ignis Group SRL. First-time payments may take up to 72 working hours after processing; previous recipients should receive payment immediately.</p>
	          </div>
	        </div>
        ${officialConfirmationMaterialsHtml(role, styles)}
        ${officialContactsHtml(contacts, role, styles)}
        <div style="${styles.section}">
          <h2 style="${styles.sectionTitle}">TRAVEL AND COMMUTING</h2>
          <p style="${styles.paragraph};margin-bottom:0;">${travel.html}</p>
        </div>
        ${finalInstructionsHtml}
        ${actionTagsHtml}
        <p style="${styles.paragraph};font-weight:600;">Thank you very much for your collaboration and commitment! 💙</p>
        <p style="margin:0;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Warm regards,</p>
        <p style="margin:4px 0 0;color:#00506b;font:700 15px/1.55 Arial, Helvetica, sans-serif;">Path International Examinations</p>
      </div>
    </div>
  `;
  const feeText = feeLines.map((line) => `${line.label}: ${line.value}`).join("\n");
  const text = [
    "OFFICIAL CONFIRMATION",
    "Path exam session official confirmation",
    "",
    `Dear ${fullName},`,
    "",
    "Hope you’re doing very well.",
    "",
    "⏳ Participation awaiting your confirmation",
    "",
    `We’re pleased to inform you that you have been selected as ${roleData.article} ${role} for the upcoming Path exam session, subject to your confirmation.`,
    "",
    "EXAM SESSION INFORMATION",
    `🗓️ Date\n${sessionDate}`,
    `🕗 Time\n${timeLabel} GMT-3 (Please make sure to arrive at least ${arrival} minutes before the session begins)`,
    "💻 Format\nOnsite",
    `📍 Venue\n${address}`,
    "",
    "FEES AND INVOICE",
    "Below you’ll find the breakdown of your exam session fee:",
    feeText,
    `TOTAL FEE: ${totalFee}`,
	    "Once all your exam sessions are over, please send one consolidated invoice to finance@pathexaminations.com, including only the sum of the total fees for all your sessions. Do not include additional expenses, as only invoices matching the system amount will be processed. The invoice may be issued in your name or someone else’s name. Please follow the attached sample with the required company details: https://drive.google.com/drive/u/0/my-drive",
	    `Payments will be processed on ${nextPaymentDate} at 5:00 pm (GMT-3) and will appear as Bellis Ignis Group SRL. First-time payments may take up to 72 working hours after processing; previous recipients should receive payment immediately.`,
    materialsText,
    officialContactsText(contacts, role),
    "TRAVEL AND COMMUTING",
    travel.text,
    finalInstructionsText,
    "We’d appreciate it if you could confirm receipt of this email and verify that you can access all the materials mentioned above.",
    `Click here to confirm participation and material reception:\n${confirmMailto}`,
    `Click here to ask a question before confirming:\n${questionMailto}`,
    `Click here to decline participation in this session:\n${declineMailto}`,
    "Thank you very much for your collaboration and commitment! 💙",
    "",
    "Warm regards,",
    "Path International Examinations",
  ].filter(Boolean).join("\n\n");
  return { html: bodyHtml, text };
};

const showStaffOfficialConfirmationEmailFeedback = showStaffPreconfirmationEmailFeedback;

const syncStaffOfficialConfirmationEmailButtons = (root = document) => {
  root.querySelectorAll?.("[data-staff-confirmation-email]").forEach((button) => {
    const panel = button.closest("[data-session-modal-panel]");
    const row = button.closest("[data-supervisor-row]");
    const viewOnly = document.querySelector("main[data-current-menu-can-edit='false']") !== null;
    const hasMember = Boolean(row?.querySelector("[data-team-member-select]")?.value);
    const onsite = panel?.dataset.sessionFormat === "Onsite";
    button.disabled = viewOnly || !hasMember || !onsite;
    button.title = !onsite
      ? "Official confirmation email is only available for onsite sessions."
      : !hasMember
        ? "Select a staff member before copying the official confirmation email."
        : "Copy official confirmation email";
  });
};

const initStaffOfficialConfirmationEmailButtons = (root = document) => {
  syncStaffOfficialConfirmationEmailButtons(root);
  root.querySelectorAll("[data-staff-confirmation-email]").forEach((button) => {
    if (button.dataset.staffOfficialConfirmationInitialized === "true") return;
    button.dataset.staffOfficialConfirmationInitialized = "true";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      if (button.disabled) return;
      const payload = buildStaffOfficialConfirmationEmail(button);
      if (payload.error) {
        showStaffOfficialConfirmationEmailFeedback(button, payload.error, true);
        return;
      }
      try {
        await copyRichTextToClipboard(payload);
        showStaffOfficialConfirmationEmailFeedback(button, "Official confirmation email copied.");
      } catch (error) {
        showStaffOfficialConfirmationEmailFeedback(button, "Could not copy the official confirmation email. Please try again.", true);
      }
    });
  });
};

if (typeof document !== "undefined") initStaffOfficialConfirmationEmailButtons();

const initInvitationEmailCopyButtons = (root = document) => {
  root.querySelectorAll("[data-copy-invitation-email]").forEach((button) => {
    const state = invitationEmailButtonState(button);
    button.disabled = !state.enabled;
    button.title = state.title;
    button.setAttribute("aria-label", state.title);
    button.classList.toggle("is-disabled", !state.enabled);
    if (state.enabled) delete button.dataset.rowLockDisabled;
    if (button.dataset.invitationInitialized === "true") return;
    button.dataset.invitationInitialized = "true";
    button.addEventListener("click", async () => {
      if (button.disabled) return;
      const payload = buildInvitationEmail(button);
      if (!payload) return;
      try {
        await copyRichTextToClipboard(payload);
        button.classList.add("is-copied");
        button.title = "Copied!";
        window.setTimeout(() => {
          button.classList.remove("is-copied");
          button.title = "Copy invitation email";
        }, 1400);
      } catch (error) {
        button.classList.add("is-error");
        window.setTimeout(() => {
          button.classList.remove("is-error");
        }, 1400);
      }
    });
  });
};

const syncStaffMemberAddressButton = (select) => {
  const button = select.closest(".staff-member-select-row")?.querySelector("[data-staff-address-copy]");
  if (!button) return;
  const option = selectedTeamMemberOption(select);
  const fullAddress = option?.dataset.fullAddress || "";
  button.dataset.copyText = fullAddress;
  button.disabled = !fullAddress;
  button.classList.toggle("is-disabled", !fullAddress);
};

const initTeamMemberSelects = (root = document) => {
  root.querySelectorAll("[data-team-member-select]").forEach((select) => {
    if (select.dataset.initialized === "true") return;
    select.dataset.initialized = "true";
    const row = select.closest(".staff-member-select-row");
    const picker = row?.querySelector("[data-team-member-picker]");
    initStaffPickerSearch(
      picker,
      "[data-team-member-search]",
      "[data-team-member-option]",
      "[data-team-member-search-empty]",
      positionTeamMemberPickerPanel
    );
    row?.querySelectorAll("[data-team-member-option]").forEach((option) => {
      option.addEventListener("click", () => {
        if (option.disabled) return;
        select.value = option.dataset.value || "";
        row.querySelector("[data-team-member-picker]").open = false;
        resetStaffPickerSearch(picker, "[data-team-member-search]", "[data-team-member-option]", "[data-team-member-search-empty]");
        refreshTeamMemberSessionCounts();
        syncTeamMemberSelect(select);
        markStaffChangesUnsaved(select.closest("[data-session-members-form]"));
        syncSupervisorMemberAvailability(select.closest("[data-session-members-form]"));
        syncSameDateAssignmentConflictAlerts();
      });
    });
    row?.querySelector("[data-team-member-picker]")?.addEventListener("toggle", (event) => {
      if (event.currentTarget.open) {
        document.querySelectorAll("[data-team-member-picker][open]").forEach((picker) => {
          if (picker !== event.currentTarget) picker.open = false;
        });
        resetStaffPickerSearch(event.currentTarget, "[data-team-member-search]", "[data-team-member-option]", "[data-team-member-search-empty]");
        positionTeamMemberPickerPanel(event.currentTarget);
        window.requestAnimationFrame(() => event.currentTarget.querySelector("[data-team-member-search]")?.focus({ preventScroll: true }));
      }
    });
    syncTeamMemberSelect(select);
  });
  root.querySelectorAll("[data-staff-address-copy]").forEach((button) => {
    if (button.dataset.initialized === "true") return;
    button.dataset.initialized = "true";
    button.addEventListener("click", async () => {
      if (!button.dataset.copyText) return;
      try {
        await copyTextToClipboard(button.dataset.copyText);
        button.classList.add("is-copied");
        window.setTimeout(() => {
          button.classList.remove("is-copied");
        }, 1200);
      } catch (error) {
        button.classList.add("is-error");
        window.setTimeout(() => {
          button.classList.remove("is-error");
        }, 1200);
      }
    });
  });
  initInvitationEmailCopyButtons(root);
  initPotentialInvitationEmailButtons(root);
  initPotentialOutcomeEmailButtons(root);
  initInterviewInvitationEmailButtons(root);
  initEntryAcceptedEmailButtons(root);
  initEntryAcceptedWhatsAppButtons(root);
  initPotentialGmailButtons(root);
  initStaffPreconfirmationEmailButtons(root);
};

document.querySelectorAll("[data-copy-link]").forEach((button) => {
  if (button.dataset.initialized === "true") return;
  button.dataset.initialized = "true";
  button.addEventListener("click", async () => {
    const originalText = button.textContent;
    try {
      await copyTextToClipboard(button.dataset.copyLink || "");
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = originalText;
      }, 1200);
    } catch (error) {
      button.textContent = "Error";
      window.setTimeout(() => {
        button.textContent = originalText;
      }, 1200);
    }
  });
});

initPotentialInvitationEmailButtons();
initPotentialOutcomeEmailButtons();
initInterviewInvitationEmailButtons();
initEntryAcceptedEmailButtons();
initEntryAcceptedWhatsAppButtons();
initPotentialGmailButtons();
initStaffPreconfirmationEmailButtons();
initPotentialSessionMultiselects();
initNoteRecipientSelects();

document.addEventListener("click", (event) => {
  document.querySelectorAll("[data-team-member-picker][open]").forEach((picker) => {
    if (!picker.contains(event.target)) picker.open = false;
  });
});

document.addEventListener("keydown", (event) => {
  const opener = event.target.closest('[data-open-modal][role="button"]');
  if (!opener || !["Enter", " "].includes(event.key)) return;
  event.preventDefault();
  opener.click();
});

const initCopyTextButtons = (root = document) => {
  root.querySelectorAll("[data-copy-text]").forEach((button) => {
    if (button.dataset.initialized === "true") return;
    button.dataset.initialized = "true";
    button.addEventListener("click", async () => {
      const feedback = button.querySelector(".copy-button-feedback");
      const defaultFeedback = feedback?.textContent || "Copied.";
      const successMessage = button.dataset.copySuccess || defaultFeedback;
      const errorMessage = button.dataset.copyError || "Could not copy the payment WhatsApp message. Please try again.";
      const showFeedback = (message, isError = false) => {
        if (feedback) feedback.textContent = message;
        button.classList.toggle("is-error", isError);
        button.classList.toggle("is-copied", !isError);
        window.setTimeout(() => {
          button.classList.remove("is-error", "is-copied");
          if (feedback) feedback.textContent = defaultFeedback;
        }, isError ? 2600 : 1400);
      };
      if (button.dataset.copyError) {
        showFeedback(errorMessage, true);
        return;
      }
      try {
        await copyTextToClipboard(button.dataset.copyText || "");
        showFeedback(successMessage);
      } catch (error) {
        showFeedback(errorMessage, true);
      }
    });
  });
};

initCopyTextButtons();

const initFinanceConceptEditor = () => {
  const form = document.querySelector("[data-finance-concept-form]");
  if (!form) return;
  const title = form.querySelector("[data-finance-concept-form-title]");
  const conceptIdInput = form.querySelector("[data-finance-concept-id]");
  const nameInput = form.querySelector("[data-finance-concept-name]");
  const descriptionInput = form.querySelector("[data-finance-concept-description]");
  const appliesToInput = form.querySelector("[data-finance-concept-applies-to]");
  const activeInput = form.querySelector("input[name='is_active']");
  const createButton = form.querySelector("[data-finance-concept-create-button]");
  const saveButton = form.querySelector("[data-finance-concept-save-button]");
  const deleteButton = form.querySelector("[data-finance-concept-delete-button]");
  const deleteActionTemplate = form.dataset.deleteAction || "";

  document.querySelectorAll("[data-edit-finance-concept]").forEach((button) => {
    button.addEventListener("click", () => {
      const conceptId = button.dataset.conceptId || "";
      if (conceptIdInput) conceptIdInput.value = conceptId;
      if (nameInput) nameInput.value = button.dataset.conceptName || "";
      if (descriptionInput) descriptionInput.value = button.dataset.conceptDescription || "";
      if (appliesToInput) appliesToInput.value = button.dataset.conceptAppliesTo || "Both";
      if (activeInput) activeInput.checked = button.dataset.conceptActive === "1";
      if (title) title.textContent = "Edit concept";
      if (createButton) createButton.hidden = true;
      if (saveButton) saveButton.hidden = false;
      if (deleteButton) {
        deleteButton.hidden = false;
        if (deleteActionTemplate && conceptId) {
          deleteButton.setAttribute("formaction", deleteActionTemplate.replace("/0/", `/${conceptId}/`));
        }
      }
      nameInput?.focus();
    });
  });

  deleteButton?.addEventListener("click", (event) => {
    if (!window.confirm("Are you sure you want to delete this finance concept? This action cannot be undone.")) {
      event.preventDefault();
    }
  });
};

initFinanceConceptEditor();

const initFinanceManagementReviewActions = () => {
  document.querySelectorAll(".finance-management-review-actions").forEach((form) => {
    const comments = form.querySelector("[data-management-review-comments]");
    if (!comments) return;
    comments.addEventListener("input", () => comments.setCustomValidity(""));
    form.querySelectorAll("[data-requires-management-comment]").forEach((button) => {
      button.addEventListener("click", (event) => {
        if (comments.value.trim()) {
          comments.setCustomValidity("");
          return;
        }
        comments.setCustomValidity("Management comments are required for this action.");
        comments.reportValidity();
        event.preventDefault();
      });
    });
  });
};

initFinanceManagementReviewActions();

const initFinancePaymentExecutionActions = () => {
  document.querySelectorAll(".finance-payment-execution-actions").forEach((form) => {
    const proofInput = form.querySelector("[data-payment-proof-input]");
    if (!proofInput) return;
    const requiredProofMessage = form.dataset.requiredPaymentProofMessage || "Payment proof is required to complete a payment.";
    const emptyProofMessage = form.dataset.emptyPaymentProofMessage || "Payment proof must be empty to continue.";
    proofInput.addEventListener("input", () => proofInput.setCustomValidity(""));
    form.querySelectorAll("[data-requires-payment-proof]").forEach((button) => {
      button.addEventListener("click", (event) => {
        if (proofInput.value.trim()) {
          proofInput.setCustomValidity("");
          return;
        }
        proofInput.setCustomValidity(button.dataset.requiredPaymentProofMessage || requiredProofMessage);
        proofInput.reportValidity();
        event.preventDefault();
      });
    });
    form.querySelectorAll("[data-requires-empty-payment-proof]").forEach((button) => {
      button.addEventListener("click", (event) => {
        if (!proofInput.value.trim()) {
          proofInput.setCustomValidity("");
          return;
        }
        proofInput.setCustomValidity(button.dataset.emptyPaymentProofMessage || emptyProofMessage);
        proofInput.reportValidity();
        event.preventDefault();
      });
    });
  });
};

initFinancePaymentExecutionActions();

const syncFinancePayeeMenu = (picker) => {
  if (!picker) return;
  const input = picker.querySelector("[data-finance-payee-input]");
  const menu = picker.querySelector("[data-finance-payee-menu]");
  if (!input || !menu) return;
  const emptyMessage = picker.dataset.financeContactKind === "client" ? "No saved clients." : "No saved contacts.";
  const query = input.value.trim().toLowerCase();
  let visibleCount = 0;
  menu.querySelectorAll("[data-finance-payee-option]").forEach((option) => {
    const name = option.dataset.contactName || "";
    const visible = !query || name.toLowerCase().includes(query);
    option.hidden = !visible;
    if (visible) visibleCount += 1;
  });
  let empty = menu.querySelector("[data-finance-payee-empty]");
  if (!empty && visibleCount === 0) {
    empty = document.createElement("div");
    empty.className = "finance-payee-empty";
    empty.dataset.financePayeeEmpty = "true";
    empty.textContent = emptyMessage;
    menu.append(empty);
  }
  if (empty) empty.textContent = emptyMessage;
  if (empty) empty.hidden = visibleCount > 0;
};

const openFinancePayeeMenu = (picker) => {
  const menu = picker?.querySelector?.("[data-finance-payee-menu]");
  if (!menu) return;
  syncFinancePayeeMenu(picker);
  menu.hidden = false;
};

const applyFinancePayeeDefaults = (picker, option) => {
  const form = picker?.closest?.("form");
  if (!form || !option) return;
  const setField = (name, value) => {
    const field = form.querySelector(`[name="${name}"]`);
    if (!field) return;
    field.value = value || "";
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
  };
  setField("concept_id", option.dataset.conceptId);
  setField("currency", option.dataset.currency);
  setField("payment_method", option.dataset.paymentMethod);
  syncFinancePaymentMethodFields(form);
  setField("account_holder", option.dataset.accountHolder);
  setField("account_number", option.dataset.accountNumber);
  setField("alias", option.dataset.alias);
  setField("tax_id", option.dataset.taxId);
  setField("client_tax_id", option.dataset.taxId);
  setField("vat_status_invoice_type", option.dataset.vatStatus);
  syncFinanceVatAddressFields(form);
  setField("client_full_address", option.dataset.fullAddress);
};

const closeFinancePayeeMenus = (exceptPicker = null) => {
  document.querySelectorAll("[data-finance-payee-picker]").forEach((picker) => {
    if (picker === exceptPicker) return;
    const menu = picker.querySelector("[data-finance-payee-menu]");
    if (menu) menu.hidden = true;
  });
};

document.addEventListener("focusin", (event) => {
  const input = event.target.closest?.("[data-finance-payee-input]");
  if (!input) return;
  const picker = input.closest("[data-finance-payee-picker]");
  closeFinancePayeeMenus(picker);
  openFinancePayeeMenu(picker);
});

document.addEventListener("input", (event) => {
  const input = event.target.closest?.("[data-finance-payee-input]");
  if (!input) return;
  openFinancePayeeMenu(input.closest("[data-finance-payee-picker]"));
});

document.addEventListener("click", async (event) => {
  const selectButton = event.target.closest?.("[data-finance-payee-select]");
  if (selectButton) {
    const picker = selectButton.closest("[data-finance-payee-picker]");
    const option = selectButton.closest("[data-finance-payee-option]");
    const input = picker?.querySelector("[data-finance-payee-input]");
    if (input && option) {
      input.value = option.dataset.contactName || selectButton.textContent.trim();
      input.dispatchEvent(new Event("input", { bubbles: true }));
      applyFinancePayeeDefaults(picker, option);
      picker.querySelector("[data-finance-payee-menu]").hidden = true;
      input.focus();
    }
    return;
  }

  const forgetButton = event.target.closest?.("[data-finance-payee-forget]");
  if (forgetButton) {
    const option = forgetButton.closest("[data-finance-payee-option]");
    const contactId = option?.dataset.contactId;
    const formData = new FormData();
    formData.append("csrf_token", document.querySelector("input[name='csrf_token']")?.value || "");
    forgetButton.disabled = true;
    try {
      const response = await fetch(forgetButton.dataset.action || "", {
        method: "POST",
        body: formData,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.message || "Unable to remove contact.");
      const contactKind = option?.dataset.contactKind || option?.closest("[data-finance-payee-picker]")?.dataset.financeContactKind || "payee";
      document.querySelectorAll(`[data-finance-payee-option][data-contact-kind="${CSS.escape(contactKind)}"][data-contact-id="${CSS.escape(contactId || String(payload.contact_id || ""))}"]`).forEach((matchingOption) => {
        const picker = matchingOption.closest("[data-finance-payee-picker]");
        matchingOption.remove();
        syncFinancePayeeMenu(picker);
      });
    } catch (error) {
      forgetButton.disabled = false;
      window.alert("The contact could not be removed from the list. Please try again.");
    }
    return;
  }

  if (!event.target.closest?.("[data-finance-payee-picker]")) closeFinancePayeeMenus();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!event.target.closest?.("[data-finance-payee-picker]")) return;
  closeFinancePayeeMenus();
});

const syncFinanceVatAddressFields = (root = document) => {
  const addressRequiredStatuses = new Set([
    "Responsable Inscripto (factura A)",
    "Monotributista (factura A)",
    "IVA Sujeto Exento (factura B)",
    "International clients (factura E)",
  ]);
  root.querySelectorAll("[data-finance-vat-status]").forEach((select) => {
    const form = select.closest("form") || document;
    const addressField = form.querySelector("[data-finance-full-address-field]");
    if (!addressField) return;
    const input = addressField.querySelector("input, textarea");
    const shouldShow = addressRequiredStatuses.has(select.value);
    addressField.hidden = !shouldShow;
    if (input) {
      input.disabled = !shouldShow;
      input.required = shouldShow;
      if (!shouldShow) input.value = "";
    }
  });
};

syncFinanceVatAddressFields();

document.addEventListener("change", (event) => {
  if (!event.target.closest?.("[data-finance-vat-status]")) return;
  syncFinanceVatAddressFields(event.target.closest("form") || document);
});

const syncFinancePaymentMethodFields = (root = document) => {
  root.querySelectorAll("[data-finance-payment-method]").forEach((select) => {
    const form = select.closest("form") || document;
    const bankFields = form.querySelector("[data-finance-bank-fields]");
    const cardFields = form.querySelector("[data-finance-card-fields]");
    const showBankFields = ["Bank transfer", "Deposit"].includes(select.value);
    const showCardFields = select.value === "Card";
    if (bankFields) {
      bankFields.hidden = !showBankFields;
      bankFields.querySelectorAll("input, select, textarea").forEach((field) => {
        field.disabled = !showBankFields;
      });
    }
    if (cardFields) {
      cardFields.hidden = !showCardFields;
      cardFields.querySelectorAll("input, select, textarea").forEach((field) => {
        field.disabled = !showCardFields;
      });
    }
    syncFinanceBankRequirement(form);
  });
};

syncFinancePaymentMethodFields();

const normalizeFinanceAmountInput = (input) => {
  if (!input) return;
  const normalized = input.value.replace(/,/g, ".");
  if (normalized !== input.value) input.value = normalized;
};

document.addEventListener("input", (event) => {
  const amountInput = event.target.closest?.("[data-finance-amount]");
  if (!amountInput) return;
  normalizeFinanceAmountInput(amountInput);
});

document.addEventListener("change", (event) => {
  if (!event.target.closest?.("[data-finance-payment-method]")) return;
  const form = event.target.closest("form") || document;
  syncFinancePaymentMethodFields(form);
  syncFinancePaymentDateFields(form);
});

function syncFinanceBankRequirement(form) {
  if (!form?.querySelector?.("[data-finance-payment-method]")) return;
  const paymentMethod = form.querySelector("[data-finance-payment-method]")?.value || "";
  const accountHolder = form.querySelector("input[name='account_holder']");
  const accountNumber = form.querySelector("input[name='account_number']");
  const alias = form.querySelector("input[name='alias']");
  if (!accountHolder || !accountNumber || !alias) return;
  const needsBankDetails = ["Bank transfer", "Deposit"].includes(paymentMethod);
  const holderMessage = needsBankDetails && !accountHolder.value.trim()
    ? "Account holder is required for bank transfer/deposit."
    : "";
  const hasBankIdentifier = Boolean(accountNumber.value.trim() || alias.value.trim());
  const identifierMessage = needsBankDetails && !hasBankIdentifier
    ? "CBU / CVU or Alias is required for bank transfer/deposit."
    : "";
  accountHolder.setCustomValidity(holderMessage);
  accountNumber.setCustomValidity(identifierMessage);
  alias.setCustomValidity(identifierMessage);
}

document.addEventListener("input", (event) => {
  if (!event.target.closest?.("input[name='account_holder'], input[name='account_number'], input[name='alias']")) return;
  syncFinanceBankRequirement(event.target.closest("form"));
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest?.("form");
  if (!form?.querySelector?.("[data-finance-payment-method]")) return;
  form.classList.add("is-validation-attempted");
  form.querySelectorAll("[data-finance-amount]").forEach(normalizeFinanceAmountInput);
  syncFinanceBankRequirement(form);
  if (!form.checkValidity()) {
    event.preventDefault();
    form.reportValidity();
  }
}, true);

document.addEventListener("invalid", (event) => {
  const form = event.target.closest?.("form");
  if (!form?.querySelector?.("[data-finance-payment-method]")) return;
  form.classList.add("is-validation-attempted");
}, true);

const syncFinancePaymentDateFields = (root = document) => {
  const forms = root.matches?.("form") ? [root] : Array.from(root.querySelectorAll?.("form") || []);
  forms.forEach((form) => {
    const group = form.querySelector("[data-finance-payment-date-options]");
    if (!group) return;
    const specificDate = form.querySelector("[data-finance-specific-payment-date]");
    const paymentMethod = form.querySelector("[data-finance-payment-method]")?.value || "";
    const cardStatus = form.querySelector("input[name='card_payment_status']:checked")?.value || "";
    const hidePaymentDate = paymentMethod === "Card" && cardStatus === "Already paid";
    const receiptRow = form.querySelector("[data-finance-card-receipt-row]");
    const receiptInput = receiptRow?.querySelector("input[name='payment_proof_url']");
    if (receiptRow) {
      receiptRow.hidden = !hidePaymentDate;
      receiptRow.setAttribute("aria-hidden", hidePaymentDate ? "false" : "true");
    }
    if (receiptInput) {
      receiptInput.disabled = !hidePaymentDate;
      receiptInput.required = hidePaymentDate;
      if (!hidePaymentDate && receiptInput.setCustomValidity) receiptInput.setCustomValidity("");
    }
    group.hidden = hidePaymentDate;
    group.setAttribute("aria-hidden", hidePaymentDate ? "true" : "false");
    group.querySelectorAll("input, select, textarea").forEach((field) => {
      field.disabled = hidePaymentDate;
    });
    if (hidePaymentDate) {
      if (specificDate) {
        specificDate.classList.remove("is-visible");
        specificDate.setAttribute("aria-hidden", "true");
        const warning = specificDate.querySelector("[data-finance-business-date-warning]");
        if (warning) warning.hidden = true;
        specificDate.querySelectorAll("input, select, textarea").forEach((field) => {
          field.disabled = true;
          field.required = false;
          if (field.setCustomValidity) field.setCustomValidity("");
        });
      }
      return;
    }
    const selected = group.querySelector("[data-finance-payment-date-mode]:checked")?.value || "asap";
    const showSpecificDate = selected === "specific";
    if (specificDate) {
      specificDate.classList.toggle("is-visible", showSpecificDate);
      specificDate.setAttribute("aria-hidden", showSpecificDate ? "false" : "true");
      specificDate.querySelectorAll("input, select, textarea").forEach((field) => {
        field.disabled = !showSpecificDate;
        field.required = showSpecificDate;
        if (!showSpecificDate && field.setCustomValidity) field.setCustomValidity("");
      });
      const warning = specificDate.querySelector("[data-finance-business-date-warning]");
      if (warning && !showSpecificDate) warning.hidden = true;
    }
  });
};

syncFinancePaymentDateFields();

document.addEventListener("change", (event) => {
  const paymentDateMode = event.target.closest?.("[data-finance-payment-date-mode]");
  if (paymentDateMode) {
    const group = paymentDateMode.closest("[data-finance-payment-date-options]");
    if (group && paymentDateMode.value === "specific") {
      group.dataset.financeSpecificDateSeen = "true";
    }
    if (group && paymentDateMode.value === "asap" && group.dataset.financeSpecificDateSeen === "true") {
      const recalculated = group.querySelector("[data-finance-payment-date-recalculated]");
      const runDate = group.querySelector("[data-finance-payment-run-date]");
      if (recalculated) recalculated.value = "1";
      if (runDate && group.dataset.nextPaymentRunDisplay) runDate.textContent = group.dataset.nextPaymentRunDisplay;
    }
  }
  if (!paymentDateMode && !event.target.closest?.("input[name='card_payment_status']")) return;
  syncFinancePaymentDateFields(event.target.closest("form") || document);
});

const staffPaymentStatus = (invoiceChecked, paymentChecked) => {
  if (invoiceChecked && paymentChecked) return "Completed";
  if (invoiceChecked) return "Verified";
  return "Pending";
};

const staffPaymentStatusBadgeHtml = (status) => `<span class="badge status-${status.toLowerCase().replace(/\s+/g, "-")}">${status}</span>`;

const showStaffPaymentFeedback = (message) => {
  const feedback = document.querySelector("[data-staff-payment-feedback]");
  if (!feedback) return;
  feedback.hidden = false;
  feedback.innerHTML = "";
  const item = document.createElement("div");
  item.className = "flash error";
  appendFlashContent(item, message);
  feedback.append(item);
};

const syncStaffPaymentRow = async (row) => {
  if (!row) return;
  const invoice = row.querySelector("[data-staff-payment-invoice]");
  const payment = row.querySelector("[data-staff-payment-payment]");
  const paymentLabel = payment?.closest(".staff-payment-checkbox");
  const statusCell = row.querySelector("[data-staff-payment-status-cell]");
  if (!invoice || !payment || !statusCell) return;

  if (!invoice.checked) {
    payment.checked = false;
    payment.disabled = true;
    paymentLabel?.classList.add("is-disabled");
  } else {
    payment.disabled = false;
    paymentLabel?.classList.remove("is-disabled");
  }

  statusCell.innerHTML = staffPaymentStatusBadgeHtml(staffPaymentStatus(invoice.checked, payment.checked));

  const formData = new FormData();
  formData.append("csrf_token", document.querySelector("input[name='csrf_token']")?.value || "");
  formData.append("invoice_verified", invoice.checked ? "1" : "0");
  formData.append("payment_completed", payment.checked ? "1" : "0");

  try {
    const response = await fetch(row.dataset.action || "", {
      method: "POST",
      body: formData,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.message || "Unable to update staff payment.");
    invoice.checked = Boolean(payload.invoice_verified);
    payment.checked = Boolean(payload.payment_completed);
    payment.disabled = !invoice.checked;
    paymentLabel?.classList.toggle("is-disabled", !invoice.checked);
    statusCell.innerHTML = staffPaymentStatusBadgeHtml(payload.status || staffPaymentStatus(invoice.checked, payment.checked));
  } catch (error) {
    showStaffPaymentFeedback(error.message);
  }
};

document.querySelectorAll("[data-staff-payment-row]").forEach((row) => {
  const invoice = row.querySelector("[data-staff-payment-invoice]");
  const payment = row.querySelector("[data-staff-payment-payment]");
  invoice?.addEventListener("change", () => syncStaffPaymentRow(row));
  payment?.addEventListener("change", () => {
    if (payment.checked && !invoice?.checked) {
      payment.checked = false;
      return;
    }
    syncStaffPaymentRow(row);
  });
});

const positionSessionCountDetail = (popover) => {
  const chip = popover?.querySelector(".session-count-chip");
  const detail = popover?.querySelector(".session-count-detail");
  if (!chip || !detail) return;
  const rect = chip.getBoundingClientRect();
  const margin = 10;
  const detailWidth = detail.offsetWidth || 260;
  const left = Math.min(
    Math.max(rect.left + rect.width / 2, detailWidth / 2 + margin),
    window.innerWidth - detailWidth / 2 - margin
  );
  const preferredTop = rect.bottom + margin;
  const detailHeight = detail.offsetHeight || 120;
  const top = preferredTop + detailHeight > window.innerHeight - margin
    ? Math.max(margin, rect.top - detailHeight - margin)
    : preferredTop;
  detail.style.setProperty("--session-popover-left", `${left}px`);
  detail.style.setProperty("--session-popover-top", `${top}px`);
};

document.querySelectorAll(".session-count-popover").forEach((popover) => {
  const detail = popover.querySelector(".session-count-detail");
  if (!detail) return;
  const show = () => {
    detail.classList.add("is-floating");
    positionSessionCountDetail(popover);
  };
  const hide = () => {
    detail.classList.remove("is-floating");
  };
  popover.addEventListener("mouseenter", show);
  popover.addEventListener("mouseleave", hide);
  popover.addEventListener("focusin", show);
  popover.addEventListener("focusout", hide);
});

window.addEventListener("scroll", () => {
  document.querySelectorAll(".session-count-detail.is-floating").forEach((detail) => {
    positionSessionCountDetail(detail.closest(".session-count-popover"));
  });
}, true);

window.addEventListener("resize", () => {
  document.querySelectorAll(".session-count-detail.is-floating").forEach((detail) => {
    positionSessionCountDetail(detail.closest(".session-count-popover"));
  });
});

const STAFF_PARTICIPATION_CLASSES = [
  "participation-pending",
  "participation-pre-confirmation-sent",
  "participation-pre-confirmed",
  "participation-official-confirmation-sent",
  "participation-confirmed",
  "participation-sent",
];

const STAFF_LOGISTICS_CLASSES = [
  "staff-logistics-does-not-apply",
  "staff-logistics-simple-logistics",
  "staff-logistics-complex-logistics",
];

const staffStatusClass = (prefix, value) => `${prefix}-${(value || "").toLowerCase().replace(/\s+/g, "-")}`;

const syncStaffHeaderParticipationTag = (row, value) => {
  const tag = row?.querySelector("[data-staff-header-participation]");
  if (!tag) return;
  tag.classList.remove(...STAFF_PARTICIPATION_CLASSES);
  tag.classList.add(staffStatusClass("participation", value));
  tag.textContent = value || "Pending";
};

const syncStaffHeaderLogisticsTag = (row, value) => {
  const tag = row?.querySelector("[data-staff-header-logistics]");
  if (!tag) return;
  tag.classList.remove(...STAFF_LOGISTICS_CLASSES);
  const logisticsClass = {
    "Does not apply": "staff-logistics-does-not-apply",
    "Uber": "staff-logistics-simple-logistics",
    "Simple logistics": "staff-logistics-simple-logistics",
    "Complex logistics": "staff-logistics-complex-logistics",
  }[value] || "staff-logistics-does-not-apply";
  tag.classList.add(logisticsClass);
  tag.textContent = value || "Does not apply";
};

const syncParticipationSelect = (select) => {
  const row = staffAssignmentRow(select);
  syncPotentialEntryParticipationOptions(row);
  const teamMemberSelect = row?.querySelector("[data-team-member-select]");
  if (teamMemberSelect && !teamMemberSelect.value && select.value !== "Pending") {
    select.value = "Pending";
  }
  select.classList.remove(
    ...STAFF_PARTICIPATION_CLASSES,
  );
  select.classList.add(staffStatusClass("participation", select.value));
  syncStaffHeaderParticipationTag(row, select.value);
  const chip = select.closest(".staff-card-field")?.querySelector("[data-fee-state-chip]");
  if (chip) {
    const isLive = EXAM_SESSION_PLANNER_PARTICIPATION_STATUSES.has(select.value);
    const isLocked = !isLive;
    chip.textContent = isLocked ? "Locked" : "Live calculation";
    chip.classList.toggle("is-live", isLive);
    chip.classList.toggle("is-locked", isLocked);
    chip.hidden = !isLive && !isLocked;
  }
  syncCalculatedFieldLocks(row);
  syncInvitationEmailCopyButtons(select.closest("[data-session-members-form]"));
  if (EXAM_SESSION_PLANNER_PARTICIPATION_STATUSES.has(select.value)) {
    syncLiveFeeCalculations(row, { forceEmpty: true });
  } else {
    syncAssignmentTotalFee(row);
  }
};

const initParticipationSelects = (root = document) => {
  root.querySelectorAll("[data-participation-select]").forEach((select) => {
    if (select.dataset.initialized === "true") return;
    select.dataset.initialized = "true";
    select.addEventListener("change", () => {
      markStaffChangesUnsaved(select.closest("[data-session-members-form]"));
      syncParticipationSelect(select);
    });
    syncParticipationSelect(select);
  });
};

const syncStaffCollapsibleSection = (section, expanded = null) => {
  if (!section) return;
  const shouldExpand = expanded === null ? section.classList.contains("is-collapsed") : Boolean(expanded);
  section.classList.toggle("is-collapsed", !shouldExpand);
  const toggle = section.querySelector("[data-staff-section-toggle]");
  if (!toggle) return;
  const label = section.getAttribute("aria-label") || "section";
  toggle.setAttribute("aria-expanded", shouldExpand ? "true" : "false");
  toggle.setAttribute("aria-label", `${shouldExpand ? "Collapse" : "Expand"} ${label}`);
  const icon = toggle.querySelector("span");
  if (icon) icon.textContent = shouldExpand ? "-" : "+";
};

const expandStaffCardCollapsibleSections = (root) => {
  root?.querySelectorAll?.("[data-staff-collapsible-section]").forEach((section) => {
    syncStaffCollapsibleSection(section, true);
  });
};

const initStaffCollapsibleSections = (root = document) => {
  root.querySelectorAll("[data-staff-collapsible-section]").forEach((section) => {
    const toggle = section.querySelector("[data-staff-section-toggle]");
    if (!toggle) return;
    syncStaffCollapsibleSection(section, !section.classList.contains("is-collapsed"));
  });
};

document.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-staff-section-toggle]");
  if (!toggle) return;
  const section = toggle.closest("[data-staff-collapsible-section]");
  if (!section) return;
  event.preventDefault();
  syncStaffCollapsibleSection(section);
});

const logisticsConceptRows = (form) => Array.from(form?.querySelectorAll("[data-logistics-concept-row]") || []);

const formHasLogisticsConcepts = (form) => logisticsConceptRows(form).length > 0;

const logisticsControls = (form) => Array.from(form?.querySelectorAll("[data-logistics-control]") || []);

const logisticsControlIsActive = (control) => ["Uber", "Complex logistics"].includes(control?.value);

const activeLogisticsControls = (form) => logisticsControls(form).filter(logisticsControlIsActive);

const rowHasActiveLogisticsControl = (row) => Array.from(row?.querySelectorAll("[data-logistics-control]") || []).some(logisticsControlIsActive);

function syncLogisticsStaffMemberLists(form) {
  if (!form) return;
  const complexStaffMembers = [];
  const seenStaffMemberIds = new Set();
  form.querySelectorAll("[data-supervisor-row]").forEach((row) => {
    const logisticsControl = row.querySelector("[data-logistics-control]");
    const teamInput = row.querySelector("[data-team-member-select]");
    const selectedOption = selectedTeamMemberOption(teamInput);
    const staffMemberId = teamInput?.value || "";
    if (
      logisticsControl?.value !== "Complex logistics"
      || !staffMemberId
      || staffMemberId.startsWith("potential:")
      || selectedOption?.dataset.entryType === "potential"
      || seenStaffMemberIds.has(staffMemberId)
    ) {
      return;
    }
    seenStaffMemberIds.add(staffMemberId);
    complexStaffMembers.push({
      id: staffMemberId,
      name: selectedOption?.dataset.name || row.querySelector("[data-staff-card-title]")?.textContent.trim() || "Staff member",
    });
  });

  form.querySelectorAll("[data-logistics-staff-list]").forEach((list) => {
    const selectedIds = new Set(
      Array.from(list.querySelectorAll("input[type='checkbox']:checked"))
        .map((checkbox) => checkbox.value)
        .concat((list.dataset.selectedStaffIds || "").split(","))
        .map((value) => value.trim())
        .filter(Boolean)
    );
    const row = list.closest("[data-logistics-concept-row]");
    const rowKeyInput = row?.querySelector("input[name='logistics_concept_row_keys']");
    const rowKey = rowKeyInput?.value || "";
    list.innerHTML = "";
    if (!complexStaffMembers.length || !rowKey) {
      const empty = document.createElement("span");
      empty.className = "logistics-staff-empty";
      empty.textContent = "No Complex logistics staff";
      list.appendChild(empty);
      list.dataset.selectedStaffIds = "";
      return;
    }
    complexStaffMembers.forEach((staffMember) => {
      const label = document.createElement("label");
      label.className = "logistics-staff-member-option";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.name = `logistics_staff_member_ids_${rowKey}`;
      checkbox.value = staffMember.id;
      checkbox.checked = selectedIds.has(staffMember.id);
      checkbox.addEventListener("change", () => {
        list.dataset.selectedStaffIds = Array.from(list.querySelectorAll("input[type='checkbox']:checked"))
          .map((item) => item.value)
          .join(",");
        syncLogisticsStatusSelect(row?.querySelector("[data-logistics-status]"));
        markStaffChangesUnsaved(form);
      });
      const text = document.createElement("span");
      text.textContent = staffMember.name;
      text.title = staffMember.name;
      label.append(checkbox, text);
      list.appendChild(label);
    });
    list.dataset.selectedStaffIds = Array.from(list.querySelectorAll("input[type='checkbox']:checked"))
      .map((item) => item.value)
      .join(",");
  });
}

const syncStaffLogisticsControl = (control) => {
  if (!control) return;
  control.classList.remove(
    ...STAFF_LOGISTICS_CLASSES,
  );
  const logisticsClass = {
    "Does not apply": "staff-logistics-does-not-apply",
    "Uber": "staff-logistics-simple-logistics",
    "Simple logistics": "staff-logistics-simple-logistics",
    "Complex logistics": "staff-logistics-complex-logistics",
  }[control.value] || "staff-logistics-does-not-apply";
  control.classList.add(logisticsClass);
  const row = control.closest("[data-supervisor-row]");
  syncStaffHeaderLogisticsTag(row, control.value);
  const hiddenInput = row?.querySelector("[data-logistics-enabled-input]");
  if (hiddenInput) hiddenInput.value = logisticsControlIsActive(control) ? "1" : "";
  syncLogisticsStaffMemberLists(control.closest("[data-session-members-form]"));
};

const syncSessionLogisticsActivityBadge = (form) => {
  const sessionId = form?.dataset.sessionId || "";
  if (!sessionId) return;
  const cell = document.querySelector(`[data-session-logistics-status-cell][data-session-id="${sessionId}"]`);
  if (!cell) return;
  const active = activeLogisticsControls(form).length > 0 || formHasLogisticsConcepts(form);
  cell.innerHTML = active
    ? '<span class="badge logistics-activity-yes">Yes</span>'
    : '<span class="centered-dash muted">-</span>';
};

const syncLogisticsPlannedState = (section) => {
  if (!section) return;
  const checkbox = section.querySelector("[data-logistics-planned]");
  const addButton = section.querySelector("[data-add-logistics-concept]");
  if (!checkbox || !addButton) return;
  const planned = checkbox.checked;
  addButton.disabled = planned;
  addButton.classList.toggle("is-disabled", planned);
  addButton.setAttribute("aria-disabled", planned ? "true" : "false");
  section.querySelectorAll("[data-logistics-concept-row]").forEach(syncLogisticsDeleteButton);
};

const syncLogisticsDeleteButton = (row) => {
  const deleteButton = row?.querySelector("[data-delete-logistics-concept]");
  if (!deleteButton) return;
  const section = row.closest("[data-logistics-section]");
  const planned = Boolean(section?.querySelector("[data-logistics-planned]")?.checked);
  const status = row.querySelector("[data-logistics-status]")?.value || "Pending";
  const canDelete = !planned && ["Pending", "In progress"].includes(status);
  deleteButton.disabled = !canDelete;
  deleteButton.setAttribute("aria-disabled", canDelete ? "false" : "true");
};

const logisticsRowCanBeConfirmed = (row) => {
  const providerSelect = row?.querySelector("[data-logistics-provider-select]");
  const hasProvider = Array.from(providerSelect?.selectedOptions || []).some((option) => option.value);
  const hasStaffMember = Boolean(row?.querySelector("[data-logistics-staff-list] input[type='checkbox']:checked"));
  return hasProvider && hasStaffMember;
};

const syncLogisticsSection = (form) => {
  if (!form) return;
  const section = form.querySelector("[data-logistics-section]");
  if (!section) return;
  section.hidden = activeLogisticsControls(form).length === 0 && !formHasLogisticsConcepts(form);
  syncLogisticsPlannedState(section);
  syncSessionLogisticsActivityBadge(form);
};

const logisticsUrlIsValid = (value) => {
  if (!value.trim()) return true;
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) && Boolean(parsed.hostname);
  } catch (error) {
    return false;
  }
};

const syncLogisticsFilesLink = (section) => {
  const input = section?.querySelector("[data-logistics-files-url]");
  const link = section?.querySelector("[data-logistics-files-link]");
  const error = section?.querySelector("[data-logistics-url-error]");
  const configureButton = section?.querySelector("[data-configure-logistics-link]");
  const editButton = section?.querySelector("[data-edit-logistics-link]");
  const field = section?.querySelector(".logistics-files-field");
  if (!input || !link) return true;
  const value = input.value.trim();
  const valid = logisticsUrlIsValid(value);
  if (error) error.textContent = valid ? "" : "Please enter a valid link.";
  link.classList.toggle("is-disabled", !value || !valid);
  link.toggleAttribute("aria-disabled", !value || !valid);
  if (configureButton) configureButton.hidden = Boolean(value && valid);
  if (editButton) editButton.hidden = !Boolean(value && valid);
  if (field && value && valid) field.hidden = true;
  if (value && valid) {
    link.href = value;
  } else {
    link.removeAttribute("href");
  }
  return valid;
};

const syncLogisticsStatusSelect = (select) => {
  if (!select) return;
  const row = select.closest("[data-logistics-concept-row]");
  const confirmedOption = Array.from(select.options || []).find((option) => option.value === "Confirmed");
  const canConfirm = logisticsRowCanBeConfirmed(row);
  if (confirmedOption) confirmedOption.disabled = !canConfirm;
  if (select.value === "Confirmed" && !canConfirm) {
    select.value = "Pending";
    delete select.dataset.logisticsConfirmedAuthorized;
  }
  select.classList.remove(
    "logistics-status-pending",
    "logistics-status-in-progress",
    "logistics-status-pre-confirmed",
    "logistics-status-confirmed",
  );
  const statusClass = {
    Pending: "logistics-status-pending",
    "In progress": "logistics-status-in-progress",
    "Pre-confirmed": "logistics-status-pre-confirmed",
    Confirmed: "logistics-status-confirmed",
  }[select.value] || "logistics-status-pending";
  select.classList.add(statusClass);
  const locked = ["Pre-confirmed", "Confirmed"].includes(select.value);
  row?.classList.toggle("is-row-locked", locked);
  const chip = row?.querySelector("[data-logistics-lock-chip]");
  if (chip) chip.hidden = !locked;
  row?.querySelectorAll("button").forEach((button) => {
    if (button.matches("[data-logistics-notes-button]")) {
      button.disabled = false;
      delete button.dataset.rowLockDisabled;
      return;
    }
    if (button.matches("[data-provider-details-button]")) {
      button.disabled = !button.dataset.providerDetailIds;
      delete button.dataset.rowLockDisabled;
      return;
    }
    if (locked) {
      if (!button.disabled) button.dataset.rowLockDisabled = "true";
      button.disabled = true;
    } else if (button.dataset.rowLockDisabled === "true") {
      button.disabled = false;
      delete button.dataset.rowLockDisabled;
    }
  });
  syncLogisticsDeleteButton(row);
  syncInvitationEmailCopyButtons(select.closest("[data-session-members-form]"));
};

const complexLogisticsCoverageError = (form) => {
  if (!form) return "";
  const requiredMembers = new Map();
  form.querySelectorAll("[data-supervisor-row]").forEach((row) => {
    const logisticsControl = row.querySelector("[data-logistics-control]");
    const teamInput = row.querySelector("[data-team-member-select]");
    const staffMemberId = teamInput?.value || "";
    if (
      logisticsControl?.value === "Complex logistics"
      && staffMemberId
      && !staffMemberId.startsWith("potential:")
    ) {
      requiredMembers.set(staffMemberId, row.querySelector("[data-staff-card-title]")?.textContent.trim() || "Staff member");
    }
  });
  if (!requiredMembers.size) return "";
  const coveredMemberIds = new Set(
    Array.from(form.querySelectorAll("[data-logistics-staff-list] input[type='checkbox']:checked"))
      .map((checkbox) => checkbox.value)
      .filter(Boolean)
  );
  const missingNames = Array.from(requiredMembers)
    .filter(([staffMemberId]) => !coveredMemberIds.has(staffMemberId))
    .map(([, name]) => name);
  if (!missingNames.length) return "";
  return `Each Complex logistics staff member must be selected in at least one Logistics concept before saving: ${missingNames.join(", ")}`;
};

const LOGISTICS_CONFIRMED_PASSWORD = "Check";
let pendingLogisticsConfirmedSelect = null;

const closeLogisticsConfirmedPasswordModal = () => {
  const modal = document.getElementById("logistics-confirmed-password-modal");
  if (!modal) return;
  const form = modal.querySelector("[data-logistics-confirm-password-form]");
  form?.reset();
  const error = modal.querySelector("[data-logistics-confirm-password-error]");
  if (error) error.textContent = "";
  pendingLogisticsConfirmedSelect = null;
  closeModal(modal);
};

const requestLogisticsConfirmedPassword = (select, previousValue) => {
  pendingLogisticsConfirmedSelect = select;
  select.dataset.previousLogisticsStatus = previousValue || "Pending";
  select.value = select.dataset.previousLogisticsStatus;
  syncLogisticsStatusSelect(select);
  const modal = document.getElementById("logistics-confirmed-password-modal");
  const input = modal?.querySelector("[data-logistics-confirm-password]");
  const error = modal?.querySelector("[data-logistics-confirm-password-error]");
  if (input) input.value = "";
  if (error) error.textContent = "";
  openModal("logistics-confirmed-password-modal", { opener: select });
  window.requestAnimationFrame(() => input?.focus({ preventScroll: true }));
};

const syncLogisticsProviderDetailsButton = (select) => {
  const row = select.closest("[data-logistics-concept-row]");
  const button = row?.querySelector("[data-provider-details-button]");
  if (!button) return;
  const selectedValues = Array.from(select.selectedOptions || [])
    .map((option) => option.value)
    .filter(Boolean);
  if (selectedValues.length > 0) {
    delete button.dataset.openModal;
    button.dataset.providerDetailIds = selectedValues.join(",");
    button.disabled = false;
    button.title = selectedValues.length === 1
      ? "Provider details"
      : `Provider details for ${selectedValues.length} providers`;
  } else {
    delete button.dataset.openModal;
    delete button.dataset.providerDetailIds;
    button.disabled = true;
    button.title = "Provider details";
  }
};

const logisticsProviderDetailsModalId = "logistics-provider-details-selected";

const ensureLogisticsProviderDetailsModal = () => {
  let modal = document.getElementById(logisticsProviderDetailsModalId);
  if (modal) return modal;
  modal = document.createElement("div");
  modal.className = "modal nested-modal logistics-provider-details-modal";
  modal.id = logisticsProviderDetailsModalId;
  modal.setAttribute("aria-hidden", "true");
  modal.innerHTML = `
    <div class="modal-panel">
      <div class="modal-header">
        <div>
          <h2 data-logistics-provider-details-title>Provider details</h2>
          <p data-logistics-provider-details-subtitle></p>
        </div>
        <button class="icon-button" type="button" data-close-modal>&times;</button>
      </div>
      <div class="logistics-provider-details-list" data-logistics-provider-details-list></div>
    </div>
  `;
  document.body.appendChild(modal);
  return modal;
};

const renderLogisticsProviderDetailsModal = (providerIds) => {
  const modal = ensureLogisticsProviderDetailsModal();
  const title = modal.querySelector("[data-logistics-provider-details-title]");
  const subtitle = modal.querySelector("[data-logistics-provider-details-subtitle]");
  const list = modal.querySelector("[data-logistics-provider-details-list]");
  if (!list) return modal;
  list.innerHTML = "";
  const uniqueProviderIds = Array.from(new Set(providerIds.filter(Boolean)));
  if (title) title.textContent = uniqueProviderIds.length === 1 ? "Provider details" : "Provider details";
  if (subtitle) {
    subtitle.textContent = uniqueProviderIds.length === 1
      ? "1 selected provider"
      : `${uniqueProviderIds.length} selected providers`;
  }

  uniqueProviderIds.forEach((providerId) => {
    const sourceModal = document.getElementById(`provider-details-${providerId}`);
    const sourcePanel = sourceModal?.querySelector(".modal-panel");
    const sourceHeader = sourcePanel?.querySelector(".modal-header > div");
    const sourceGrid = sourcePanel?.querySelector(".provider-details-grid");
    if (!sourceHeader || !sourceGrid) return;

    const article = document.createElement("article");
    article.className = "logistics-provider-details-card";

    const header = document.createElement("header");
    header.className = "logistics-provider-details-card-header";
    header.innerHTML = sourceHeader.innerHTML;

    const grid = sourceGrid.cloneNode(true);
    article.append(header, grid);
    list.appendChild(article);
  });

  if (!list.children.length) {
    const empty = document.createElement("p");
    empty.className = "empty-history";
    empty.textContent = "No provider details available.";
    list.appendChild(empty);
  }
  return modal;
};

const selectedLogisticsProviderOptions = (select) => Array.from(select?.selectedOptions || [])
  .filter((option) => option.value && !option.disabled && !option.hidden);

const syncLogisticsProviderPicker = (select) => {
  const picker = select?._logisticsProviderPicker;
  if (!picker) return;
  const selectedOptions = selectedLogisticsProviderOptions(select);
  const buttonText = picker.querySelector("[data-logistics-provider-picker-text]");
  const summary = picker.querySelector("summary");
  const tags = picker.querySelector("[data-logistics-provider-picker-tags]");
  const clearButton = picker.querySelector("[data-logistics-provider-clear]");
  const checkboxes = picker.querySelectorAll("input[type='checkbox']");
  const selectedProviderLabels = selectedOptions.map((option) => option.textContent.trim());
  const selectedProviderTitle = selectedProviderLabels.join("\n");

  checkboxes.forEach((checkbox) => {
    const option = Array.from(select.options).find((item) => item.value === checkbox.value);
    checkbox.checked = Boolean(option?.selected);
    checkbox.disabled = Boolean(option?.disabled || option?.hidden || select.disabled);
    checkbox.closest("[data-logistics-provider-option]")?.toggleAttribute("hidden", checkbox.disabled);
  });

  if (buttonText) {
    if (select.disabled) {
      buttonText.textContent = "Select type first";
      buttonText.removeAttribute("title");
    } else if (selectedOptions.length === 0) {
      buttonText.textContent = "Select providers";
      buttonText.removeAttribute("title");
    } else if (selectedOptions.length === 1) {
      buttonText.textContent = selectedProviderLabels[0];
      buttonText.title = selectedProviderLabels[0];
    } else {
      buttonText.textContent = `${selectedOptions.length} providers selected`;
      buttonText.title = selectedProviderTitle;
    }
  }
  if (summary) {
    if (selectedProviderTitle) summary.title = selectedProviderTitle;
    else summary.removeAttribute("title");
  }

  if (clearButton) clearButton.hidden = selectedOptions.length === 0 || select.disabled;
  picker.classList.toggle("has-selection", selectedOptions.length > 0);
  picker.classList.toggle("is-disabled", select.disabled);

  if (!tags) return;
  tags.innerHTML = "";
  selectedOptions.slice(0, 3).forEach((option) => {
    const chip = document.createElement("span");
    chip.className = "logistics-provider-chip";
    chip.title = option.textContent.trim();
    chip.textContent = option.textContent.trim();

    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${option.textContent.trim()}`);
    remove.textContent = "x";
    remove.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      option.selected = false;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    chip.appendChild(remove);
    tags.appendChild(chip);
  });
  if (selectedOptions.length > 3) {
    const overflow = document.createElement("span");
    overflow.className = "logistics-provider-chip is-overflow";
    overflow.textContent = `+${selectedOptions.length - 3}`;
    tags.appendChild(overflow);
  }
};

const closeOtherLogisticsProviderPickers = (activePicker) => {
  document.querySelectorAll("[data-logistics-provider-picker][open]").forEach((picker) => {
    if (picker !== activePicker) picker.open = false;
  });
};

const positionLogisticsProviderPickerPanel = (picker) => {
  const panel = picker?.querySelector(".logistics-provider-picker-panel");
  const summary = picker?.querySelector("summary");
  if (!panel || !summary || !picker.open) return;
  const rect = summary.getBoundingClientRect();
  const viewportGap = 12;
  const panelWidth = Math.min(Math.max(rect.width, 320), window.innerWidth - viewportGap * 2);
  const left = Math.min(Math.max(rect.left, viewportGap), window.innerWidth - panelWidth - viewportGap);
  const availableBelow = window.innerHeight - rect.bottom - viewportGap;
  const availableAbove = rect.top - viewportGap;
  const openAbove = availableBelow < 220 && availableAbove > availableBelow;
  const maxHeight = Math.max(180, Math.min(320, openAbove ? availableAbove - 6 : availableBelow - 6));
  panel.style.width = `${panelWidth}px`;
  panel.style.maxHeight = `${maxHeight}px`;
  panel.style.left = `${left}px`;
  const panelHeight = Math.min(panel.scrollHeight || maxHeight, maxHeight);
  panel.style.top = openAbove
    ? `${Math.max(viewportGap, rect.top - panelHeight - 6)}px`
    : `${Math.min(window.innerHeight - viewportGap, rect.bottom + 6)}px`;
};

const initLogisticsProviderPicker = (select) => {
  if (select._logisticsProviderPicker) return;
  select.classList.add("native-logistics-provider-select");

  const picker = document.createElement("details");
  picker.className = "logistics-provider-picker";
  picker.dataset.logisticsProviderPicker = "true";

  const summary = document.createElement("summary");
  summary.innerHTML = '<span data-logistics-provider-picker-text>Select providers</span><span aria-hidden="true">⌄</span>';

  const panel = document.createElement("div");
  panel.className = "logistics-provider-picker-panel";
  panel.setAttribute("role", "listbox");
  panel.setAttribute("aria-multiselectable", "true");

  const actions = document.createElement("div");
  actions.className = "logistics-provider-picker-actions";
  const clearButton = document.createElement("button");
  clearButton.type = "button";
  clearButton.dataset.logisticsProviderClear = "true";
  clearButton.textContent = "Clear";
  clearButton.addEventListener("click", (event) => {
    event.preventDefault();
    Array.from(select.options).forEach((option) => {
      option.selected = false;
    });
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  actions.appendChild(clearButton);
  panel.appendChild(actions);

  const options = Array.from(select.options).filter((option) => option.value);
  if (options.length) {
    options.forEach((option) => {
      const row = document.createElement("label");
      row.className = "logistics-provider-picker-option";
      row.dataset.logisticsProviderOption = "true";
      row.setAttribute("role", "option");

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = option.value;
      checkbox.checked = option.selected;

      const check = document.createElement("span");
      check.className = "logistics-provider-option-check";
      check.textContent = "✓";
      check.setAttribute("aria-hidden", "true");

      const text = document.createElement("span");
      text.className = "logistics-provider-option-text";
      text.textContent = option.textContent.trim();

      checkbox.addEventListener("change", () => {
        option.selected = checkbox.checked;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });

      row.append(checkbox, check, text);
      panel.appendChild(row);
    });
  } else {
    const empty = document.createElement("span");
    empty.className = "logistics-provider-picker-empty";
    empty.textContent = "No providers available";
    panel.appendChild(empty);
  }

  const tags = document.createElement("div");
  tags.className = "logistics-provider-picker-tags";
  tags.dataset.logisticsProviderPickerTags = "true";

  picker.append(summary, panel, tags);
  select.insertAdjacentElement("afterend", picker);
  select._logisticsProviderPicker = picker;
  summary.addEventListener("click", (event) => {
    if (!select.disabled) return;
    event.preventDefault();
  });
  picker.addEventListener("toggle", () => {
    if (picker.open) {
      closeOtherLogisticsProviderPickers(picker);
      positionLogisticsProviderPickerPanel(picker);
    }
  });
  syncLogisticsProviderPicker(select);
};

const syncLogisticsProviderForType = (typeSelect) => {
  const row = typeSelect.closest("[data-logistics-concept-row]");
  const providerSelect = row?.querySelector("[data-logistics-provider-select]");
  if (!providerSelect) return;
  const selectedTypeId = typeSelect.value;
  let selectedProviderIsAvailable = true;
  Array.from(providerSelect.options).forEach((option) => {
    if (!option.value) {
      option.hidden = false;
      option.disabled = false;
      return;
    }
    const matchesSelectedType = Boolean(selectedTypeId) && option.dataset.providerTypeId === selectedTypeId;
    option.hidden = !matchesSelectedType;
    option.disabled = !matchesSelectedType;
    if (option.selected && !matchesSelectedType) selectedProviderIsAvailable = false;
  });
  providerSelect.disabled = !selectedTypeId;
  if (!selectedTypeId || !selectedProviderIsAvailable) {
    Array.from(providerSelect.options).forEach((option) => {
      option.selected = false;
    });
  }
  syncLogisticsProviderDetailsButton(providerSelect);
  syncLogisticsProviderPicker(providerSelect);
  syncLogisticsStatusSelect(row?.querySelector("[data-logistics-status]"));
};

const syncLogisticsCurrencySelect = (select) => {
  select.classList.remove(
    "logistics-currency-ars",
    "logistics-currency-eur",
    "logistics-currency-gbp",
    "logistics-currency-usd",
    "logistics-currency-uyu",
  );
  select.classList.add(`logistics-currency-${String(select.value || "ars").toLowerCase()}`);
};

const normalizeLogisticsFeeInput = (input) => {
  input.value = input.value.replace(/\./g, "").replace(/[^0-9,]/g, "");
  const commaIndex = input.value.indexOf(",");
  if (commaIndex !== -1) {
    input.value = `${input.value.slice(0, commaIndex + 1)}${input.value.slice(commaIndex + 1).replace(/,/g, "")}`;
  }
};

const roundLogisticsFeeInput = (input) => {
  const value = input.value.trim();
  if (!value) return;
  const parsed = Number.parseFloat(value.replace(",", "."));
  if (!Number.isFinite(parsed) || parsed < 0) {
    input.value = "";
    return;
  }
  const integerPart = Math.floor(parsed);
  const decimalPart = parsed - integerPart;
  input.value = String(decimalPart > 0.5 ? integerPart + 1 : integerPart);
};

const logisticsRowKey = (row) => {
  const input = row?.querySelector("input[name='logistics_concept_row_keys']");
  return input?.value || "";
};

const draftLogisticsModalId = (rowKey) => `logistics-draft-history-${rowKey}`;

const draftNoteTimestamp = () => {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())} GMT-3`;
};

const renderDraftLogisticsNote = (list, note) => {
  const entry = document.createElement("article");
  entry.className = "history-entry";
  const time = document.createElement("time");
  time.textContent = `${draftNoteTimestamp()} | Pending save`;
  const text = document.createElement("p");
  text.textContent = note;
  entry.append(time, text);
  list.prepend(entry);
};

const syncLogisticsNotesButtonCount = (row) => {
  const button = row?.querySelector("[data-logistics-notes-button]");
  if (!button) return;
  const savedCount = Number.parseInt(button.dataset.logisticsNoteCount || "0", 10) || 0;
  const rowKey = logisticsRowKey(row);
  const pendingCount = rowKey ? row.querySelectorAll(`input[name="logistics_note_${rowKey}"]`).length : 0;
  const total = savedCount + pendingCount;
  button.textContent = total > 0 ? `Notes (${total})` : "Notes";
};

const ensureDraftLogisticsHistoryModal = (row) => {
  const rowKey = logisticsRowKey(row);
  if (!rowKey) return null;
  const existingModal = document.getElementById(draftLogisticsModalId(rowKey));
  if (existingModal) return existingModal;

  const modal = document.createElement("div");
  modal.className = "modal nested-modal";
  modal.id = draftLogisticsModalId(rowKey);
  modal.setAttribute("aria-hidden", "true");
  modal.innerHTML = `
    <div class="modal-panel">
      <div class="modal-header">
        <h2>History</h2>
        <button class="icon-button" type="button" data-close-modal>&times;</button>
      </div>
      <details class="history-add-panel" open>
        <summary class="secondary-button compact-action">Add note</summary>
        <div class="form-grid one-column history-add-form">
          <label>
            New note
            <textarea rows="4" maxlength="4000" placeholder="Add a new history note" data-draft-logistics-note required></textarea>
          </label>
          <div class="form-actions">
            <button class="primary-button" type="button" data-save-draft-logistics-note>Add note</button>
          </div>
        </div>
      </details>
      <div class="history-list" data-draft-logistics-notes hidden></div>
      <p class="empty-history" data-draft-logistics-empty>No history recorded.</p>
    </div>
  `;
  modal.dataset.logisticsRowKey = rowKey;
  document.body.appendChild(modal);
  return modal;
};

const initLogisticsControls = (root = document) => {
  root.querySelectorAll("select[data-logistics-status]").forEach((select) => {
    if (select.dataset.logisticsStatusInitialized === "true") return;
    select.dataset.logisticsStatusInitialized = "true";
    select.dataset.previousLogisticsStatus = select.value || "Pending";
    select.addEventListener("focus", () => {
      select.dataset.previousLogisticsStatus = select.value || "Pending";
    });
    select.addEventListener("change", () => {
      const previousValue = select.dataset.previousLogisticsStatus || "Pending";
      const row = select.closest("[data-logistics-concept-row]");
      const providerTypeSelect = row?.querySelector("[data-logistics-provider-type]");
      if (select.value !== "Pending" && !providerTypeSelect?.value) {
        select.value = previousValue || "Pending";
        syncLogisticsStatusSelect(select);
        select.dataset.previousLogisticsStatus = select.value || "Pending";
        window.alert("Select a Type of provider before changing this Logistics concept from Pending.");
        providerTypeSelect?.focus();
        return;
      }
      if (select.value === "Confirmed" && previousValue !== "Confirmed" && select.dataset.logisticsConfirmedAuthorized !== "true") {
        requestLogisticsConfirmedPassword(select, previousValue);
        return;
      }
      if (select.value !== "Confirmed") {
        delete select.dataset.logisticsConfirmedAuthorized;
      }
      syncLogisticsStatusSelect(select);
      select.dataset.previousLogisticsStatus = select.value || "Pending";
    });
    syncLogisticsStatusSelect(select);
  });

  root.querySelectorAll(".logistics-provider-select").forEach((select) => {
    if (select.dataset.logisticsProviderInitialized === "true") return;
    select.dataset.logisticsProviderInitialized = "true";
    initLogisticsProviderPicker(select);
    select.addEventListener("change", () => {
      syncLogisticsProviderDetailsButton(select);
      syncLogisticsProviderPicker(select);
      syncLogisticsStatusSelect(select.closest("[data-logistics-concept-row]")?.querySelector("[data-logistics-status]"));
    });
    syncLogisticsProviderDetailsButton(select);
    syncLogisticsProviderPicker(select);
  });

  root.querySelectorAll("[data-logistics-provider-type]").forEach((select) => {
    if (select.dataset.logisticsProviderTypeInitialized === "true") return;
    select.dataset.logisticsProviderTypeInitialized = "true";
    select.addEventListener("change", () => syncLogisticsProviderForType(select));
    syncLogisticsProviderForType(select);
  });

  root.querySelectorAll("[data-logistics-fee]").forEach((input) => {
    if (input.dataset.logisticsFeeInitialized === "true") return;
    input.dataset.logisticsFeeInitialized = "true";
    input.addEventListener("input", () => normalizeLogisticsFeeInput(input));
    input.addEventListener("blur", () => roundLogisticsFeeInput(input));
    input.addEventListener("keydown", (event) => {
      if (["-", "+", ".", "e", "E"].includes(event.key)) event.preventDefault();
    });
  });

  root.querySelectorAll("[data-logistics-currency]").forEach((select) => {
    if (select.dataset.logisticsCurrencyInitialized === "true") return;
    select.dataset.logisticsCurrencyInitialized = "true";
    select.addEventListener("change", () => syncLogisticsCurrencySelect(select));
    syncLogisticsCurrencySelect(select);
  });

  root.querySelectorAll("[data-logistics-files-url]").forEach((input) => {
    if (input.dataset.logisticsUrlInitialized === "true") return;
    input.dataset.logisticsUrlInitialized = "true";
    input.addEventListener("input", () => syncLogisticsFilesLink(input.closest("[data-logistics-section]")));
    syncLogisticsFilesLink(input.closest("[data-logistics-section]"));
  });

  root.querySelectorAll("[data-logistics-planned]").forEach((checkbox) => {
    if (checkbox.dataset.logisticsPlannedInitialized === "true") return;
    checkbox.dataset.logisticsPlannedInitialized = "true";
    checkbox.addEventListener("change", () => {
      syncLogisticsPlannedState(checkbox.closest("[data-logistics-section]"));
      markStaffChangesUnsaved(checkbox.closest("[data-session-members-form]"));
    });
    syncLogisticsPlannedState(checkbox.closest("[data-logistics-section]"));
  });

  root.querySelectorAll("[data-configure-logistics-link]").forEach((button) => {
    if (button.dataset.logisticsLinkInitialized === "true") return;
    button.dataset.logisticsLinkInitialized = "true";
    button.addEventListener("click", () => {
      const section = button.closest("[data-logistics-section]");
      const field = section?.querySelector(".logistics-files-field");
      const input = section?.querySelector("[data-logistics-files-url]");
      if (!field || !input) return;
      field.hidden = false;
      input.focus();
    });
  });

  root.querySelectorAll("[data-edit-logistics-link]").forEach((button) => {
    if (button.dataset.logisticsLinkInitialized === "true") return;
    button.dataset.logisticsLinkInitialized = "true";
    button.addEventListener("click", () => {
      const section = button.closest("[data-logistics-section]");
      const field = section?.querySelector(".logistics-files-field");
      const input = section?.querySelector("[data-logistics-files-url]");
      if (!field || !input) return;
      field.hidden = false;
      input.focus();
      input.select();
    });
  });

  root.querySelectorAll("[data-logistics-control]").forEach((control) => {
    if (control.dataset.logisticsInitialized === "true") return;
    control.dataset.logisticsInitialized = "true";
    control.addEventListener("change", () => {
      const form = control.closest("[data-session-members-form]");
      const previousValue = control.dataset.previousLogisticsValue || "Does not apply";
      syncStaffLogisticsControl(control);
      if (!logisticsControlIsActive(control) && activeLogisticsControls(form).length === 0 && formHasLogisticsConcepts(form)) {
        window.alert("Remove all Logistics concepts before deactivating Logistics from the session.");
        control.value = previousValue;
        syncStaffLogisticsControl(control);
      }
      control.dataset.previousLogisticsValue = control.value;
      syncLogisticsSection(form);
      syncInvitationEmailCopyButtons(form);
    });
    syncStaffLogisticsControl(control);
    control.dataset.previousLogisticsValue = control.value;
  });

  root.querySelectorAll("[data-session-members-form]").forEach((form) => {
    syncLogisticsSection(form);
    syncLogisticsStaffMemberLists(form);
  });
};

const initSessionMemberRows = (root = document) => {
  initMemberMultiselects(root);
  initEmergencyContactControls(root);
  initPotentialSessionMultiselects(root);
  initNoteRecipientSelects(root);
  initTeamMemberSelects(root);
  initStaffGmailLinks(root);
  initParticipationSelects(root);
  initStaffCollapsibleSections(root);
  initLogisticsControls(root);
  initShipmentRecipientControls(root);
  initIntegerInputs(root);
  initTimeInputs(root);
  root.querySelectorAll("[data-km-input]").forEach(syncKmDisableButton);
  if (root.matches?.("[data-supervisor-row]")) {
    syncSupervisorRoleFeePlaceholder(root);
    syncDeviceDepPlaceholder(root);
    syncCommutingPlaceholder(root);
    syncFuelPlaceholder(root);
    syncVehicleDepPlaceholder(root);
    syncSeniorityPlaceholder(root);
    syncSeniority(root);
    syncFuelVehicleCells(root);
    syncRemoteKmMutualExclusion(root);
    if (rowHasManualFeeOverride(root)) {
      enableManualFeeOverride(root);
      saveManualFeeOverride(root);
    }
    syncEditFeesButton(root);
    syncAssignmentTotalFee(root);
  }
  root.querySelectorAll("[data-supervisor-row]").forEach((row) => {
    syncSupervisorRoleFeePlaceholder(row);
    syncDeviceDepPlaceholder(row);
    syncCommutingPlaceholder(row);
    syncFuelPlaceholder(row);
    syncVehicleDepPlaceholder(row);
    syncSeniorityPlaceholder(row);
    syncSeniority(row);
    syncFuelVehicleCells(row);
    syncRemoteKmMutualExclusion(row);
    if (rowHasManualFeeOverride(row)) {
      enableManualFeeOverride(row);
      saveManualFeeOverride(row);
    }
    syncEditFeesButton(row);
    syncAssignmentTotalFee(row);
  });
  syncInvitationEmailCopyButtons(root);
};

const syncShipmentRecipientControls = (form) => {
  if (!form) return;
  const selectedInput = Array.from(form.querySelectorAll("[data-shipment-recipient-input]"))
    .find((input) => !input.disabled && input.value);
  const selectedValue = selectedInput?.value || "";
  form.querySelectorAll("[data-supervisor-row]").forEach((row) => {
    const input = row.querySelector("[data-shipment-recipient-input]");
    const chip = row.querySelector("[data-shipment-recipient-chip]");
    const picker = row.querySelector("[data-shipment-recipient-picker]");
    const checkbox = row.querySelector("[data-shipment-recipient-checkbox]");
    const isSelected = Boolean(selectedValue && input?.value === selectedValue);
    if (input) input.disabled = !isSelected;
    if (chip) chip.hidden = !isSelected;
    if (picker) picker.hidden = Boolean(selectedValue);
    if (checkbox) checkbox.checked = false;
  });
};

const initShipmentRecipientControls = (root = document) => {
  const forms = new Set();
  root.querySelectorAll("[data-shipment-recipient-checkbox]").forEach((checkbox) => {
    if (checkbox.dataset.initialized === "true") return;
    checkbox.dataset.initialized = "true";
    checkbox.addEventListener("change", () => {
      const row = checkbox.closest("[data-supervisor-row]");
      const form = checkbox.closest("[data-session-members-form]");
      if (!row || !form || !checkbox.checked) return;
      form.querySelectorAll("[data-shipment-recipient-input]").forEach((input) => {
        input.disabled = true;
      });
      const input = row.querySelector("[data-shipment-recipient-input]");
      if (input) input.disabled = false;
      syncShipmentRecipientControls(form);
      markStaffChangesUnsaved(form);
    });
  });
  root.querySelectorAll("[data-clear-shipment-recipient]").forEach((button) => {
    if (button.dataset.initialized === "true") return;
    button.dataset.initialized = "true";
    button.addEventListener("click", () => {
      const form = button.closest("[data-session-members-form]");
      if (!form) return;
      form.querySelectorAll("[data-shipment-recipient-input]").forEach((input) => {
        input.disabled = true;
      });
      syncShipmentRecipientControls(form);
      markStaffChangesUnsaved(form);
    });
  });
  root.querySelectorAll("[data-session-members-form]").forEach((form) => forms.add(form));
  root.closest?.("[data-session-members-form]") && forms.add(root.closest("[data-session-members-form]"));
  forms.forEach(syncShipmentRecipientControls);
};

const initUnsavedStaffChangeTracking = (root = document) => {
  root.querySelectorAll("[data-session-members-form]").forEach((form) => {
    if (form.dataset.unsavedTrackingInitialized === "true") return;
    form.dataset.unsavedTrackingInitialized = "true";
    form.addEventListener("input", (event) => {
      if (event.target.closest("[data-session-members-form]") === form) {
        markStaffChangesUnsaved(form);
      }
    });
    form.addEventListener("change", (event) => {
      if (event.target.closest("[data-session-members-form]") === form) {
        markStaffChangesUnsaved(form);
      }
    });
  });
};

initSessionMemberRows();
initUnsavedStaffChangeTracking();
refreshTeamMemberSessionCounts();
syncSameDateAssignmentConflictAlerts();
document.querySelectorAll("[data-session-members-form]").forEach(syncSupervisorMemberAvailability);

document.querySelectorAll("[data-add-member-row]").forEach((button) => {
  button.addEventListener("click", () => {
    const form = button.closest("[data-session-members-form]");
    if (!form) return;
    const section = button.closest(".session-member-section");
    const template = section?.querySelector("[data-supervisor-row-template]");
    const target = section?.querySelector("[data-supervisor-rows]");
    if (!template || !target) return;

    const rowKey = `new-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    const wrapper = document.createElement("div");
    wrapper.innerHTML = template.innerHTML.replaceAll("__KEY__", rowKey).trim();
    const row = wrapper.firstElementChild;
    if (!row) return;
    target.prepend(row);
    initSessionMemberRows(row);
    expandStaffCardCollapsibleSections(row);
    syncSessionNonAvailableFields(form);
    markStaffChangesUnsaved(form);
    refreshTeamMemberSessionCounts();
    syncSupervisorMemberAvailability(form);
    syncSameDateAssignmentConflictAlerts();
  });
});

document.querySelectorAll("[data-add-logistics-concept]").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.disabled) return;
    const section = button.closest("[data-logistics-section]");
    const form = button.closest("[data-session-members-form]");
    const template = section?.querySelector("[data-logistics-concept-template]");
    const target = section?.querySelector("[data-logistics-concepts]");
    if (!section || !template || !target) return;
    section.hidden = false;
    const rowKey = `new-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    const wrapper = document.createElement("tbody");
    wrapper.innerHTML = template.innerHTML.replaceAll("__KEY__", rowKey).trim();
    const row = wrapper.firstElementChild;
    if (!row) return;
    target.appendChild(row);
    initLogisticsControls(row);
    syncLogisticsStaffMemberLists(form);
    markStaffChangesUnsaved(form);
    syncLogisticsSection(form);
  });
});

document.querySelector("[data-logistics-confirm-password-form]")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const input = form.querySelector("[data-logistics-confirm-password]");
  const error = form.querySelector("[data-logistics-confirm-password-error]");
  const password = input?.value.trim() || "";
  if (password !== LOGISTICS_CONFIRMED_PASSWORD) {
    if (error) error.textContent = "Incorrect password.";
    input?.focus();
    return;
  }
  if (!pendingLogisticsConfirmedSelect) {
    closeLogisticsConfirmedPasswordModal();
    return;
  }
  const sessionForm = pendingLogisticsConfirmedSelect.closest("[data-session-members-form]");
  const passwordInput = sessionForm?.querySelector("[data-logistics-confirmation-password]");
  if (passwordInput) passwordInput.value = password;
  pendingLogisticsConfirmedSelect.dataset.logisticsConfirmedAuthorized = "true";
  pendingLogisticsConfirmedSelect.value = "Confirmed";
  syncLogisticsStatusSelect(pendingLogisticsConfirmedSelect);
  pendingLogisticsConfirmedSelect.dataset.previousLogisticsStatus = "Confirmed";
  markStaffChangesUnsaved(sessionForm);
  closeLogisticsConfirmedPasswordModal();
});

document.addEventListener("click", (event) => {
  if (!event.target.closest("[data-logistics-confirm-cancel]")) return;
  event.preventDefault();
  closeLogisticsConfirmedPasswordModal();
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-provider-details-button]");
  if (!button || button.disabled) return;
  const providerIds = (button.dataset.providerDetailIds || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (!providerIds.length) return;
  event.preventDefault();
  event.stopPropagation();
  const modal = renderLogisticsProviderDetailsModal(providerIds);
  openModal(modal.id, { opener: button });
});

document.addEventListener("click", (event) => {
  const editButton = event.target.closest("[data-edit-assignment-fees]");
  if (!editButton) return;
  const row = editButton.closest("[data-supervisor-row]");
  if (!row) return;
  if (!rowHasManualFeeOverride(row)) {
    enableManualFeeOverride(row);
  } else if (row.classList.contains("is-manual-fee-editing")) {
    saveManualFeeOverride(row);
  } else {
    resetManualFeeOverride(row);
  }
});

document.addEventListener("click", (event) => {
  const removeButton = event.target.closest("[data-remove-supervisor-row]");
  if (!removeButton) return;
  const row = removeButton.closest("[data-supervisor-row]");
  const form = removeButton.closest("[data-session-members-form]");
  if (!row || !form) return;
  const sectionKey = row.dataset.sectionKey || "supervisor";
  const sectionLabel = sectionKey === "examiner" ? "examiner" : sectionKey === "intern" ? "intern" : "supervisor";
  if (rowHasActiveLogisticsControl(row) && activeLogisticsControls(form).length === 1 && formHasLogisticsConcepts(form)) {
    window.alert("Remove all Logistics concepts before deactivating Logistics from the session.");
    return;
  }
  const confirmationMessage = `Are you sure you want to permanently delete this ${sectionLabel}? This action cannot be undone.`;
  if (!window.confirm(confirmationMessage)) return;
  const assignmentInput = row.querySelector(`input[name^='${sectionKey}_assignment_id_']`);
  if (assignmentInput?.value) {
    const deletedWrap = form.querySelector("[data-deleted-assignments]");
    const deletedInput = document.createElement("input");
    deletedInput.type = "hidden";
    deletedInput.name = `deleted_${sectionKey}_assignment_ids`;
    deletedInput.value = assignmentInput.value;
    deletedWrap?.appendChild(deletedInput);
  }
  row.remove();
  markStaffChangesUnsaved(form);
  syncLogisticsSection(form);
  refreshTeamMemberSessionCounts();
  syncSupervisorMemberAvailability(form);
  syncShipmentRecipientControls(form);
  syncSameDateAssignmentConflictAlerts();
});

const markStaffMemberNonAvailable = (form, value) => {
  if (!form || !value) return false;
  const scope = sessionMembersScopeForForm(form);
  const checkbox = scope?.querySelector(`[data-session-non-available-picker] input[type='checkbox'][value="${CSS.escape(value)}"]`);
  if (!checkbox) return false;
  checkbox.checked = true;
  syncMemberMultiselect(checkbox.closest("[data-session-non-available-picker]"));
  syncSessionNonAvailableFields(form);
  return true;
};

const resetDeclinedStaffAssignmentRow = (row) => {
  const participation = row?.querySelector("[data-participation-select]");
  if (participation) {
    Array.from(participation.options).forEach((option) => {
      if (option.value === "Pending") {
        option.disabled = false;
        option.hidden = false;
      } else if (option.dataset.externalParticipationStatus === "true") {
        option.disabled = true;
        option.hidden = true;
      }
    });
    participation.value = "Pending";
  }
  const logistics = row?.querySelector("[data-logistics-control]");
  if (logistics) {
    Array.from(logistics.options).forEach((option) => {
      option.selected = option.value === "Does not apply";
    });
    logistics.value = "Does not apply";
  }
  const teamMemberInput = row?.querySelector("[data-team-member-select]");
  if (teamMemberInput) {
    teamMemberInput.value = "";
    syncTeamMemberSelect(teamMemberInput);
  }
  if (participation) {
    participation.value = "Pending";
    syncParticipationSelect(participation);
  }
  if (logistics) {
    logistics.value = "Does not apply";
    syncStaffLogisticsControl(logistics);
    logistics.dataset.previousLogisticsValue = logistics.value;
  }
  resetKmFieldToCheckbox(row);
  resetManualFeeOverride(row);
  syncLiveFeeCalculations(row, { forceEmpty: true });
};

document.addEventListener("click", (event) => {
  const declinedButton = event.target.closest("[data-staff-declined-button]");
  if (!declinedButton) return;
  event.preventDefault();
  event.stopPropagation();
  const row = declinedButton.closest("[data-supervisor-row]");
  const form = declinedButton.closest("[data-session-members-form]");
  const teamMemberInput = row?.querySelector("[data-team-member-select]");
  const selectedValue = teamMemberInput?.value || "";
  if (!row || !form || !selectedValue) return;
  if (rowHasActiveLogisticsControl(row) && activeLogisticsControls(form).length === 1 && formHasLogisticsConcepts(form)) {
    window.alert("Remove all Logistics concepts before deactivating Logistics from the session.");
    return;
  }
  if (!window.confirm("Please confirm this staff member declined their participation.")) return;
  markStaffMemberNonAvailable(form, selectedValue);
  resetDeclinedStaffAssignmentRow(row);
  markStaffChangesUnsaved(form);
  syncLogisticsSection(form);
  refreshTeamMemberSessionCounts();
  syncSupervisorMemberAvailability(form);
  syncShipmentRecipientControls(form);
  syncSameDateAssignmentConflictAlerts();
});

document.addEventListener("click", (event) => {
  const deleteButton = event.target.closest("[data-delete-logistics-concept]");
  if (!deleteButton) return;
  const row = deleteButton.closest("[data-logistics-concept-row]");
  const form = deleteButton.closest("[data-session-members-form]");
  if (!row || !form) return;
  if (!window.confirm("Are you sure you want to delete this logistics concept? This action cannot be undone.")) return;
  const conceptInput = row.querySelector("input[name^='logistics_concept_id_']");
  if (conceptInput?.value) {
    const deletedWrap = form.querySelector("[data-deleted-assignments]");
    const deletedInput = document.createElement("input");
    deletedInput.type = "hidden";
    deletedInput.name = "deleted_logistics_concept_ids";
    deletedInput.value = conceptInput.value;
    deletedWrap?.appendChild(deletedInput);
  }
  row.remove();
  markStaffChangesUnsaved(form);
  syncLogisticsSection(form);
});

document.addEventListener("click", (event) => {
  const notesButton = event.target.closest("[data-logistics-notes-button]");
  if (!notesButton || notesButton.hasAttribute("data-open-modal")) return;
  event.preventDefault();
  const row = notesButton.closest("[data-logistics-concept-row]");
  const modal = ensureDraftLogisticsHistoryModal(row);
  if (modal) openModal(modal.id);
});

document.addEventListener("click", (event) => {
  const saveButton = event.target.closest("[data-save-draft-logistics-note]");
  if (!saveButton) return;
  const modal = saveButton.closest(".modal");
  const rowKey = modal?.dataset.logisticsRowKey || "";
  const rowInput = Array.from(document.querySelectorAll('[data-logistics-concept-row] input[name="logistics_concept_row_keys"]'))
    .find((input) => input.value === rowKey);
  const row = rowInput?.closest("[data-logistics-concept-row]");
  const textarea = modal?.querySelector("[data-draft-logistics-note]");
  const note = textarea?.value.trim() || "";
  if (!row || !textarea || !note) return;

  const hiddenInput = document.createElement("input");
  hiddenInput.type = "hidden";
  hiddenInput.name = `logistics_note_${rowKey}`;
  hiddenInput.value = note;
  row.appendChild(hiddenInput);
  markStaffChangesUnsaved(row.closest("[data-session-members-form]"));

  const list = modal.querySelector("[data-draft-logistics-notes]");
  const empty = modal.querySelector("[data-draft-logistics-empty]");
  if (list) {
    list.hidden = false;
    renderDraftLogisticsNote(list, note);
  }
  if (empty) empty.hidden = true;
  syncLogisticsNotesButtonCount(row);
  textarea.value = "";
});

document.querySelectorAll("[data-session-members-form]").forEach((form) => {
  if (form.dataset.logisticsSubmitInitialized === "true") return;
  form.dataset.logisticsSubmitInitialized = "true";
  form.addEventListener("submit", (event) => {
    syncSessionNonAvailableFields(form);
    const logisticsSection = form.querySelector("[data-logistics-section]");
    if (logisticsSection && !syncLogisticsFilesLink(logisticsSection)) {
      event.preventDefault();
      logisticsSection.hidden = false;
      const field = logisticsSection.querySelector(".logistics-files-field");
      if (field) field.hidden = false;
      logisticsSection.querySelector("[data-logistics-files-url]")?.focus();
    }
    const coverageError = complexLogisticsCoverageError(form);
    if (coverageError) {
      event.preventDefault();
      if (logisticsSection) logisticsSection.hidden = false;
      window.alert(coverageError);
      form.querySelector("[data-logistics-section]")?.scrollIntoView({ block: "start", behavior: "smooth" });
    }
    form.querySelectorAll("[data-logistics-fee]").forEach(roundLogisticsFeeInput);
    if (event.defaultPrevented) return;
    const submitter = event.submitter?.matches?.("[data-session-members-save]") ? event.submitter : null;
    if (submitter) {
      let actionInput = form.querySelector("input[data-session-members-modal-action]");
      if (!actionInput) {
        actionInput = document.createElement("input");
        actionInput.type = "hidden";
        actionInput.name = "modal_action";
        actionInput.dataset.sessionMembersModalAction = "";
        form.appendChild(actionInput);
      }
      actionInput.value = submitter.value || "save_close";
    }
    const modal = form.closest(".modal");
    modal?.querySelectorAll("[data-session-members-save]").forEach((button) => {
      button.disabled = true;
    });
    if (submitter) {
      submitter.dataset.originalText = submitter.textContent;
      submitter.textContent = "Saving...";
    }
  });
});

const memberSectionHasActiveSettings = (section) => {
  if (!section) return false;
  return Array.from(section.querySelectorAll("[data-supervisor-row]")).some((row) => {
    if (row.querySelector("[data-member-multiselect] input[type='checkbox']:checked")) return true;
    if (row.querySelector("[data-team-member-select]")?.value) return true;
    const participation = row.querySelector("[data-participation-select]");
    if (participation && participation.value !== "Pending") return true;
    if (row.querySelector("[data-enable-km]:checked")) return true;
    if (row.querySelector("[data-enable-fuel-vehicle]:checked")) return true;
    return Array.from(row.querySelectorAll("input")).some((input) => {
      if (input.type === "hidden" || input.type === "checkbox") return false;
      return input.value.trim() !== "";
    });
  });
};

const clearOptionalMemberSection = (section) => {
  const form = section.closest("[data-session-members-form]");
  const deletedWrap = form?.querySelector("[data-deleted-assignments]");
  section.querySelectorAll("[data-supervisor-row]").forEach((row) => {
    const sectionKey = row.dataset.sectionKey || "intern";
    const assignmentInput = row.querySelector(`input[name^='${sectionKey}_assignment_id_']`);
    if (assignmentInput?.value && deletedWrap) {
      const deletedInput = document.createElement("input");
      deletedInput.type = "hidden";
      deletedInput.name = `deleted_${sectionKey}_assignment_ids`;
      deletedInput.value = assignmentInput.value;
      deletedWrap.appendChild(deletedInput);
    }
    row.remove();
  });
};

document.querySelectorAll("[data-toggle-optional-section]").forEach((button) => {
  button.addEventListener("click", () => {
    const section = document.getElementById(button.dataset.toggleOptionalSection || "");
    if (!section) return;
    const isHidden = section.hidden;
    if (isHidden) {
      section.hidden = false;
      button.textContent = button.dataset.deactivateLabel || "Deactivate";
      return;
    }
    if (memberSectionHasActiveSettings(section)) {
      window.alert("The Intern section cannot be deleted because there are active settings associated with it.");
      return;
    }
    clearOptionalMemberSection(section);
    section.hidden = true;
    button.textContent = button.dataset.activateLabel || "Activate";
    refreshTeamMemberSessionCounts();
    syncSupervisorMemberAvailability(button.closest("[data-session-members-form]"));
    syncSameDateAssignmentConflictAlerts();
  });
});

document.querySelectorAll("[data-toggle-certification-add]").forEach((checkbox) => {
  const target = document.getElementById(checkbox.dataset.toggleCertificationAdd);
  if (!target) return;

  const syncTarget = () => {
    target.hidden = !checkbox.checked;
  };

  checkbox.addEventListener("change", syncTarget);
  syncTarget();
});

document.querySelectorAll("[data-submit-on-change]").forEach((field) => {
  field.addEventListener("change", () => {
    const form = field.closest("form");
    if (!form) return;
    const previousValue = field.dataset.currentValue || "";
    const confirmationMessage = field.dataset.confirmCertifiedChange;
    if (confirmationMessage && previousValue === "Certified" && field.value !== "Certified") {
      if (!window.confirm(confirmationMessage)) {
        field.value = previousValue;
        return;
      }
    }
    if (form.closest("[data-annual-records-table]")) {
      saveAnnualTableScrollState();
    }
    if (form.requestSubmit) {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });
});

document.querySelectorAll(".member-form").forEach((form) => {
  const status = form.querySelector("select[name='status']");
  const arrangedFields = form.querySelector("[data-arranged-fields]");
  if (!status || !arrangedFields) return;

  const syncArrangedFields = () => {
    const isArranged = status.value === "Interview invitation sent" || status.value === "Interview confirmed" || status.value === "Induction confirmed";
    arrangedFields.hidden = !isArranged;
    arrangedFields.querySelectorAll("input, select").forEach((field) => {
      field.required = isArranged && field.dataset.arrangedOptional !== "true";
    });
  };

  status.addEventListener("change", syncArrangedFields);
  syncArrangedFields();
});

const showProviderFeedback = (message, category = "success") => {
  const stack = document.querySelector("[data-provider-feedback]");
  if (!stack) return;
  stack.hidden = false;
  stack.innerHTML = "";
  const item = document.createElement("div");
  item.className = `flash ${category}`;
  appendFlashContent(item, message);
  stack.append(item);
  window.setTimeout(() => {
    if (stack.contains(item)) {
      item.remove();
      stack.hidden = !stack.children.length;
    }
  }, 3200);
};

const providerTypeChipHtml = (name, colorKey) => `<span class="provider-type-chip ${colorKey || "provider-type-0"}">${name || ""}</span>`;

const providerTypeCellHtml = (provider) => `
  <div class="provider-type-cell-content">
    ${providerTypeChipHtml(provider.provider_type_name, provider.provider_type_color_key)}
    <span class="provider-availability-note">${provider.available_in_logistics ? "Available in exam sessions" : "Not available in exam sessions"}</span>
  </div>
`;

const syncProviderTypePreview = (form) => {
  const select = form.querySelector("[data-provider-type-select]");
  const preview = form.querySelector("[data-provider-type-preview]");
  if (!select || !preview) return;
  const option = select.selectedOptions[0];
  const hasValue = Boolean(select.value);
  preview.className = `provider-selected-type-preview provider-type-chip ${option?.dataset.colorKey || "provider-type-0"}`;
  preview.textContent = hasValue ? option.textContent : "\u00A0";
  preview.style.visibility = hasValue ? "visible" : "hidden";
};

const syncProviderFormValidity = (form) => {
  const submit = form.querySelector("[data-provider-submit]");
  if (!submit) return;
  const providerType = form.querySelector("[name='provider_type_id']")?.value || "";
  const name = form.querySelector("[name='name']")?.value.trim() || "";
  const availability = form.querySelector("[name='available_in_logistics']:checked")?.value || "";
  submit.disabled = !(providerType && name && availability);
  syncProviderTypePreview(form);
};

const providerFormData = (form) => {
  const data = new FormData(form);
  ["name", "full_address", "email", "telephone", "whatsapp", "website", "instagram", "linkedin", "type_name"].forEach((name) => {
    if (data.has(name)) data.set(name, (data.get(name) || "").trim());
  });
  return data;
};

const postProviderForm = async (form) => {
  const response = await fetch(form.action, {
    method: "POST",
    body: providerFormData(form),
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.message || "Something went wrong.");
  return payload;
};

const setProviderStars = (ratingRoot, rating) => {
  ratingRoot.dataset.rating = String(rating);
  ratingRoot.querySelectorAll("[data-rating-value]").forEach((button) => {
    const value = Number.parseInt(button.dataset.ratingValue || "0", 10);
    button.textContent = value <= rating ? "★" : "☆";
    button.setAttribute("aria-pressed", String(value === rating));
  });
};

const setProviderAddressCell = (cell, address) => {
  if (!cell) return;
  cell.textContent = "";
  if (!address) {
    const empty = document.createElement("span");
    empty.className = "muted";
    empty.textContent = "-";
    cell.appendChild(empty);
    return;
  }
  const wrapper = document.createElement("div");
  wrapper.className = "copy-address-cell";
  const text = document.createElement("span");
  text.textContent = address;
  const button = document.createElement("button");
  button.className = "copy-icon-button";
  button.type = "button";
  button.dataset.copyText = address;
  button.setAttribute("aria-label", "Copy full address");
  button.title = "Copy full address";
  button.innerHTML = `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="9" width="10" height="10" rx="2"></rect>
      <path d="M5 15V7a2 2 0 0 1 2-2h8"></path>
    </svg>
    <span class="copy-button-feedback">Copied</span>
  `;
  wrapper.append(text, button);
  cell.appendChild(wrapper);
  initCopyTextButtons(cell);
};

const setProviderStackCell = (cell, values) => {
  if (!cell) return;
  cell.textContent = "";
  const visibleValues = values.filter((value) => value);
  if (!visibleValues.length) {
    const empty = document.createElement("span");
    empty.className = "muted";
    empty.textContent = "-";
    cell.append(empty);
    return;
  }
  const stack = document.createElement("div");
  stack.className = "provider-info-stack";
  visibleValues.forEach((value) => {
    const line = document.createElement("span");
    line.textContent = value;
    stack.append(line);
  });
  cell.append(stack);
};

const renderProviderRow = (provider) => {
  const row = document.createElement("tr");
  row.dataset.providerRow = "";
  row.dataset.providerId = String(provider.id);
  row.innerHTML = `
    <td data-provider-type-cell>${providerTypeCellHtml(provider)}</td>
    <td class="strong" data-provider-name-cell></td>
    <td class="provider-address-cell" data-provider-address-cell></td>
    <td class="provider-contact-cell" data-provider-contact-cell></td>
    <td class="provider-contact-cell" data-provider-social-cell></td>
    <td><button class="mini-button" type="button" data-open-modal="provider-history-${provider.id}" data-provider-history-button>Notes</button></td>
    <td>
      <div class="provider-rating" role="radiogroup" aria-label="Experience rating" data-provider-rating data-provider-id="${provider.id}" data-rating="${provider.experience_rating}" data-action="/providers/${provider.id}/experience">
        ${[1, 2, 3, 4, 5].map((rating) => `<button type="button" class="provider-star" data-rating-value="${rating}" aria-label="${rating} star${rating === 1 ? "" : "s"}" aria-pressed="false">☆</button>`).join("")}
      </div>
    </td>
    <td><button class="mini-button" type="button" data-open-modal="edit-provider-${provider.id}">Edit</button></td>
    <td><button class="danger-button compact-action" type="button" data-open-modal="delete-provider-${provider.id}">Delete</button></td>
  `;
  row.dataset.availableInLogistics = provider.available_in_logistics ? "true" : "false";
  row.querySelector("[data-provider-name-cell]").textContent = provider.name;
  setProviderAddressCell(row.querySelector("[data-provider-address-cell]"), provider.full_address);
  setProviderStackCell(row.querySelector("[data-provider-contact-cell]"), [provider.email, provider.telephone, provider.whatsapp]);
  setProviderStackCell(row.querySelector("[data-provider-social-cell]"), [provider.website, provider.instagram, provider.linkedin]);
  setProviderStars(row.querySelector("[data-provider-rating]"), provider.experience_rating);
  return row;
};

const providerTypeOptionsHtml = (selectedId = "") => Array.from(document.querySelectorAll("[data-provider-type-select] option"))
  .map((option) => `<option value="${option.value}" data-color-key="${option.dataset.colorKey || ""}" ${String(selectedId) === option.value ? "selected" : ""}>${option.textContent}</option>`)
  .join("");

const ensureProviderModals = (provider) => {
  if (!document.getElementById(`edit-provider-${provider.id}`)) {
    const editModal = document.createElement("div");
    editModal.className = "modal";
    editModal.id = `edit-provider-${provider.id}`;
    editModal.setAttribute("aria-hidden", "true");
    editModal.dataset.providerEditModal = "";
    editModal.dataset.providerId = String(provider.id);
    editModal.innerHTML = `
      <div class="modal-panel large">
        <div class="modal-header">
          <h2>Edit provider</h2>
          <button class="icon-button" type="button" data-close-modal>&times;</button>
        </div>
        <form method="post" action="/providers/${provider.id}" class="form-grid provider-form" data-provider-form>
          <input type="hidden" name="csrf_token" value="${document.querySelector("input[name='csrf_token']")?.value || ""}">
          <label>
            Type of provider
            <div class="provider-type-field">
              <select name="provider_type_id" required data-provider-type-select>${providerTypeOptionsHtml(provider.provider_type_id)}</select>
              <button class="mini-button provider-type-action" type="button" data-open-modal="create-provider-type" aria-label="Create provider type">+</button>
              <button class="mini-button provider-type-action" type="button" data-open-modal="manage-provider-types" aria-label="Manage provider types">−</button>
            </div>
            <span class="provider-selected-type-preview provider-type-chip provider-type-0" data-provider-type-preview aria-hidden="true">&nbsp;</span>
          </label>
          <label>
            Name of provider
            <input name="name" value="" maxlength="180" required>
          </label>
          <label class="full-span">
            Full address
            <input name="full_address" value="" maxlength="500">
          </label>
          <label>
            Email
            <input type="email" name="email" value="" maxlength="254">
          </label>
          <label>
            Telephone
            <input type="tel" name="telephone" value="" maxlength="80">
          </label>
          <label>
            WhatsApp
            <input type="tel" name="whatsapp" value="" maxlength="80">
          </label>
          <label>
            Website
            <input name="website" value="" maxlength="300">
          </label>
          <label>
            Instagram
            <input name="instagram" value="" maxlength="120">
          </label>
          <label>
            LinkedIn
            <input name="linkedin" value="" maxlength="300">
          </label>
          <label class="full-span provider-availability-field">
            Available in Logistics
            <span class="field-hint">Show this provider in the Logistics section of exam sessions.</span>
            <div class="provider-radio-group" role="radiogroup" aria-label="Available in Logistics">
              <label class="provider-radio-option">
                <input type="radio" name="available_in_logistics" value="yes" required>
                <span>Yes</span>
              </label>
              <label class="provider-radio-option">
                <input type="radio" name="available_in_logistics" value="no" required>
                <span>No</span>
              </label>
            </div>
          </label>
          <div class="form-actions full-span">
            <button class="secondary-button" type="button" data-close-modal>Cancel</button>
            <button class="primary-button" type="submit" data-provider-submit disabled>Save changes</button>
          </div>
        </form>
      </div>
    `;
    editModal.querySelector("[name='name']").value = provider.name;
    editModal.querySelector("[name='full_address']").value = provider.full_address;
    editModal.querySelector("[name='email']").value = provider.email || "";
    editModal.querySelector("[name='telephone']").value = provider.telephone || "";
    editModal.querySelector("[name='whatsapp']").value = provider.whatsapp || "";
    editModal.querySelector("[name='website']").value = provider.website || "";
    editModal.querySelector("[name='instagram']").value = provider.instagram || "";
    editModal.querySelector("[name='linkedin']").value = provider.linkedin || "";
    editModal.querySelector(`[name='available_in_logistics'][value='${provider.available_in_logistics ? "yes" : "no"}']`).checked = true;
    document.body.append(editModal);
    initProviderForm(editModal.querySelector("[data-provider-form]"));
  }

  if (!document.getElementById(`delete-provider-${provider.id}`)) {
    const deleteModal = document.createElement("div");
    deleteModal.className = "modal";
    deleteModal.id = `delete-provider-${provider.id}`;
    deleteModal.setAttribute("aria-hidden", "true");
    deleteModal.innerHTML = `
      <div class="modal-panel confirm-panel">
        <div class="modal-header">
          <h2>Delete provider</h2>
          <button class="icon-button" type="button" data-close-modal>&times;</button>
        </div>
        <p>Are you sure you want to delete this provider? This action cannot be undone.</p>
        <form method="post" action="/providers/${provider.id}/delete" class="form-actions" data-provider-delete-form>
          <input type="hidden" name="csrf_token" value="${document.querySelector("input[name='csrf_token']")?.value || ""}">
          <button class="secondary-button" type="button" data-close-modal>Cancel</button>
          <button class="danger-button" type="submit">Delete</button>
        </form>
      </div>
    `;
    document.body.append(deleteModal);
    initProviderDeleteForm(deleteModal.querySelector("[data-provider-delete-form]"));
  }

  if (!document.getElementById(`provider-history-${provider.id}`)) {
    const historyModal = document.createElement("div");
    historyModal.className = "modal";
    historyModal.id = `provider-history-${provider.id}`;
    historyModal.setAttribute("aria-hidden", "true");
    historyModal.dataset.providerHistoryModal = "";
    historyModal.dataset.providerId = String(provider.id);
    historyModal.innerHTML = `
      <div class="modal-panel">
        <div class="modal-header">
          <h2>History</h2>
          <button class="icon-button" type="button" data-close-modal>&times;</button>
        </div>
        <details class="history-add-panel">
          <summary class="secondary-button compact-action">Add note</summary>
          <form method="post" action="/providers/${provider.id}/notes" class="form-grid one-column history-add-form" data-provider-history-form>
            <input type="hidden" name="csrf_token" value="${document.querySelector("input[name='csrf_token']")?.value || ""}">
            <label>
              New note
              <textarea name="interview" rows="4" maxlength="4000" placeholder="Add a new history note" required></textarea>
            </label>
            <div class="form-actions">
              <button class="primary-button" type="submit">Add note</button>
            </div>
          </form>
        </details>
        <div class="history-list" data-provider-history-list hidden></div>
        <p class="empty-history" data-provider-history-empty>No history recorded.</p>
      </div>
    `;
    document.body.append(historyModal);
    initProviderHistoryForm(historyModal.querySelector("[data-provider-history-form]"));
  }
};

const updateProviderEditForm = (provider) => {
  const modal = document.getElementById(`edit-provider-${provider.id}`);
  if (!modal) return;
  const form = modal.querySelector("[data-provider-form]");
  form.querySelector("[name='provider_type_id']").value = provider.provider_type_id;
  form.querySelector("[name='name']").value = provider.name;
  form.querySelector("[name='full_address']").value = provider.full_address;
  form.querySelector("[name='email']").value = provider.email || "";
  form.querySelector("[name='telephone']").value = provider.telephone || "";
  form.querySelector("[name='whatsapp']").value = provider.whatsapp || "";
  form.querySelector("[name='website']").value = provider.website || "";
  form.querySelector("[name='instagram']").value = provider.instagram || "";
  form.querySelector("[name='linkedin']").value = provider.linkedin || "";
  form.querySelector(`[name='available_in_logistics'][value='${provider.available_in_logistics ? "yes" : "no"}']`).checked = true;
  syncProviderFormValidity(form);
};

const addProviderTypeToSelects = (providerType) => {
  document.querySelectorAll("[data-provider-type-select]").forEach((select) => {
    if (select.querySelector(`option[value="${providerType.id}"]`)) return;
    const option = document.createElement("option");
    option.value = providerType.id;
    option.textContent = providerType.name;
    option.dataset.colorKey = providerType.color_key;
    select.append(option);
  });
};

const addProviderTypeToManageList = (providerType) => {
  const list = document.querySelector("[data-provider-type-list]");
  if (!list) return;
  const item = document.createElement("div");
  item.className = "provider-type-item";
  item.dataset.providerTypeItem = "";
  item.dataset.typeId = String(providerType.id);
  item.dataset.isSystem = "false";
  item.innerHTML = `
    ${providerTypeChipHtml(providerType.name, providerType.color_key)}
    <button class="danger-button compact-action" type="button" data-delete-provider-type data-action="/providers/types/${providerType.id}/delete">Delete</button>
  `;
  list.append(item);
};

const initProviderForm = (form) => {
  if (!form || form.dataset.providerInitialized === "true") return;
  form.dataset.providerInitialized = "true";
  form.querySelectorAll("input, select").forEach((field) => {
    field.addEventListener("input", () => syncProviderFormValidity(form));
    field.addEventListener("change", () => syncProviderFormValidity(form));
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = await postProviderForm(form);
      const table = document.querySelector("[data-providers-table]");
      const existingRow = document.querySelector(`[data-provider-row][data-provider-id="${payload.provider.id}"]`);
      if (existingRow) {
        existingRow.querySelector("[data-provider-type-cell]").innerHTML = providerTypeCellHtml(payload.provider);
        existingRow.querySelector("[data-provider-name-cell]").textContent = payload.provider.name;
        setProviderAddressCell(existingRow.querySelector("[data-provider-address-cell]"), payload.provider.full_address);
        setProviderStackCell(existingRow.querySelector("[data-provider-contact-cell]"), [payload.provider.email, payload.provider.telephone, payload.provider.whatsapp]);
        setProviderStackCell(existingRow.querySelector("[data-provider-social-cell]"), [payload.provider.website, payload.provider.instagram, payload.provider.linkedin]);
        existingRow.dataset.availableInLogistics = payload.provider.available_in_logistics ? "true" : "false";
        updateProviderEditForm(payload.provider);
      } else if (table) {
        table.querySelector("[data-providers-empty]")?.remove();
        table.prepend(renderProviderRow(payload.provider));
        ensureProviderModals(payload.provider);
        form.reset();
        syncProviderFormValidity(form);
      }
      closeModal(form.closest(".modal"));
      showProviderFeedback(payload.message, "success");
    } catch (error) {
      showProviderFeedback(error.message, "error");
    }
  });
  syncProviderFormValidity(form);
};

document.querySelectorAll("[data-provider-form]").forEach(initProviderForm);

document.querySelector("[data-provider-type-create-form]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const payload = await postProviderForm(form);
    addProviderTypeToSelects(payload.provider_type);
    addProviderTypeToManageList(payload.provider_type);
    form.reset();
    closeModal(form.closest(".modal"));
    showProviderFeedback(payload.message, "success");
  } catch (error) {
    showProviderFeedback(error.message, "error");
  }
});

document.addEventListener("click", async (event) => {
  const deleteTypeButton = event.target.closest("[data-delete-provider-type]");
  if (deleteTypeButton) {
    if (!window.confirm("Are you sure you want to delete this provider type?")) return;
    const formData = new FormData();
    const csrf = document.querySelector("input[name='csrf_token']")?.value || "";
    formData.set("csrf_token", csrf);
    try {
      const response = await fetch(deleteTypeButton.dataset.action, { method: "POST", body: formData });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.message || "Something went wrong.");
      document.querySelector(`[data-provider-type-item][data-type-id="${payload.type_id}"]`)?.remove();
      document.querySelectorAll(`[data-provider-type-select] option[value="${payload.type_id}"]`).forEach((option) => option.remove());
      showProviderFeedback(payload.message, "success");
    } catch (error) {
      showProviderFeedback(error.message, "error");
    }
    return;
  }

  const star = event.target.closest("[data-provider-rating] [data-rating-value]");
  if (star) {
    const ratingRoot = star.closest("[data-provider-rating]");
    const selected = Number.parseInt(star.dataset.ratingValue || "0", 10);
    const current = Number.parseInt(ratingRoot.dataset.rating || "0", 10);
    const nextRating = selected === current ? 0 : selected;
    const formData = new FormData();
    formData.set("csrf_token", document.querySelector("input[name='csrf_token']")?.value || "");
    formData.set("experience_rating", String(nextRating));
    try {
      const response = await fetch(ratingRoot.dataset.action, { method: "POST", body: formData });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.message || "Something went wrong.");
      setProviderStars(ratingRoot, payload.provider.experience_rating);
      showProviderFeedback(payload.message, "success");
    } catch (error) {
      showProviderFeedback(error.message, "error");
    }
    return;
  }
});

document.addEventListener("mouseover", (event) => {
  const star = event.target.closest("[data-provider-rating] [data-rating-value]");
  if (!star) return;
  const ratingRoot = star.closest("[data-provider-rating]");
  const hoverRating = Number.parseInt(star.dataset.ratingValue || "0", 10);
  ratingRoot.querySelectorAll("[data-rating-value]").forEach((button) => {
    const value = Number.parseInt(button.dataset.ratingValue || "0", 10);
    button.textContent = value <= hoverRating ? "★" : "☆";
  });
});

document.addEventListener("mouseout", (event) => {
  const ratingRoot = event.target.closest?.("[data-provider-rating]");
  if (!ratingRoot || ratingRoot.contains(event.relatedTarget)) return;
  setProviderStars(ratingRoot, Number.parseInt(ratingRoot.dataset.rating || "0", 10));
});

const initProviderDeleteForm = (form) => {
  if (!form || form.dataset.providerDeleteInitialized === "true") return;
  form.dataset.providerDeleteInitialized = "true";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = await postProviderForm(form);
      document.querySelector(`[data-provider-row][data-provider-id="${payload.provider_id}"]`)?.remove();
      document.getElementById(`edit-provider-${payload.provider_id}`)?.remove();
      document.getElementById(`delete-provider-${payload.provider_id}`)?.remove();
      document.getElementById(`provider-history-${payload.provider_id}`)?.remove();
      closeModal(form.closest(".modal"));
      showProviderFeedback(payload.message, "success");
    } catch (error) {
      showProviderFeedback(error.message, "error");
    }
  });
};

document.querySelectorAll("[data-provider-delete-form]").forEach(initProviderDeleteForm);

const initProviderHistoryForm = (form) => {
  if (!form || form.dataset.providerHistoryInitialized === "true") return;
  form.dataset.providerHistoryInitialized = "true";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = await postProviderForm(form);
      const modal = form.closest("[data-provider-history-modal]");
      const list = modal.querySelector("[data-provider-history-list]");
      const empty = modal.querySelector("[data-provider-history-empty]");
      const entry = document.createElement("article");
      entry.className = "history-entry";
      const time = document.createElement("time");
      time.textContent = `Created on: ${payload.note.created_on} h`;
      const from = document.createElement("small");
      from.textContent = `From: ${payload.note.from || "-"}`;
      const to = document.createElement("small");
      to.textContent = `To: ${payload.note.to || "-"}`;
      const text = document.createElement("p");
      text.textContent = payload.note.comment;
      entry.append(time, from);
      if (payload.note.to && payload.note.to !== "-") entry.append(to);
      entry.append(text);
      list.prepend(entry);
      list.hidden = false;
      if (empty) empty.hidden = true;
      const button = document.querySelector(`[data-provider-row][data-provider-id="${payload.provider.id}"] [data-provider-history-button]`);
      if (button) button.textContent = payload.provider.history_count > 0 ? `Notes (${payload.provider.history_count})` : "Notes";
      form.reset();
      showProviderFeedback(payload.message, "success");
    } catch (error) {
      showProviderFeedback(error.message, "error");
    }
  });
};

document.querySelectorAll("[data-provider-history-form]").forEach(initProviderHistoryForm);

const updateInductionOptionRows = (root) => {
  const maxOptions = Number.parseInt(root.dataset.maxOptions || "10", 10);
  const rows = [...root.querySelectorAll("[data-induction-option-row]")];
  root.querySelector("[data-induction-options-list]")?.classList.toggle("is-scrollable", rows.length > 2);
  const moreIndicator = root.querySelector("[data-induction-options-more]");
  if (moreIndicator) {
    const hiddenCount = Math.max(0, rows.length - 2);
    moreIndicator.hidden = hiddenCount === 0;
    moreIndicator.textContent = hiddenCount === 1
      ? "1 more option below"
      : `${hiddenCount} more options below`;
  }
  rows.forEach((row, index) => {
    row.querySelectorAll("input").forEach((input) => {
      const field = input.name.includes("start_time") ? "start time" : input.name.includes("end_time") ? "end time" : "date";
      input.setAttribute("aria-label", `Upcoming induction session option ${index + 1} ${field}`);
    });
    const addButton = row.querySelector("[data-add-induction-option]");
    const removeButton = row.querySelector("[data-remove-induction-option]");
    if (addButton) addButton.disabled = rows.length >= maxOptions;
    if (removeButton) removeButton.disabled = rows.length <= 1;
  });
};

const initInductionOptions = (root) => {
  if (!root || root.dataset.inductionOptionsInitialized === "true") return;
  root.dataset.inductionOptionsInitialized = "true";
  updateInductionOptionRows(root);
  root.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add-induction-option]");
    const removeButton = event.target.closest("[data-remove-induction-option]");
    const list = root.querySelector("[data-induction-options-list]");
    if (!list) return;
    if (addButton) {
      const rows = [...list.querySelectorAll("[data-induction-option-row]")];
      const maxOptions = Number.parseInt(root.dataset.maxOptions || "10", 10);
      if (rows.length >= maxOptions) return;
      const nextRow = rows[rows.length - 1].cloneNode(true);
      nextRow.querySelectorAll("input").forEach((input) => {
        input.value = "";
      });
      list.append(nextRow);
      updateInductionOptionRows(root);
      validateInductionTimeRange(nextRow);
      nextRow.querySelector("input")?.focus();
      return;
    }
    if (removeButton) {
      const rows = [...list.querySelectorAll("[data-induction-option-row]")];
      if (rows.length <= 1) return;
      removeButton.closest("[data-induction-option-row]")?.remove();
      updateInductionOptionRows(root);
    }
  });
  root.querySelectorAll("[data-induction-option-row]").forEach(validateInductionTimeRange);
};

document.querySelectorAll("[data-induction-options]").forEach(initInductionOptions);

document.addEventListener("toggle", (event) => {
  const panel = event.target.closest?.(".incident-impact-form-panel");
  if (!panel || !panel.open) return;
  const card = panel.closest(".incident-impact-card");
  card?.querySelectorAll(".incident-impact-form-panel[open]").forEach((otherPanel) => {
    if (otherPanel !== panel) otherPanel.removeAttribute("open");
  });
}, true);

document.addEventListener("click", (event) => {
  const closeDetailsButton = event.target.closest("[data-close-details]");
  if (!closeDetailsButton) return;
  closeDetailsButton.closest("details")?.removeAttribute("open");
});

document.addEventListener("change", (event) => {
  const editCheckbox = event.target.closest?.("[data-permission-edit]");
  if (editCheckbox) {
    const menuKey = editCheckbox.dataset.permissionEdit;
    const form = editCheckbox.closest("form") || document;
    const viewCheckbox = form.querySelector(`[data-permission-view="${CSS.escape(menuKey)}"]`);
    if (viewCheckbox && editCheckbox.checked) viewCheckbox.checked = true;
    if (menuKey === "users") updatePermissionManagementScope(form);
    return;
  }
  const viewCheckbox = event.target.closest?.("[data-permission-view]");
  if (!viewCheckbox) return;
  const menuKey = viewCheckbox.dataset.permissionView;
  const form = viewCheckbox.closest("form") || document;
  const relatedEditCheckbox = form.querySelector(`[data-permission-edit="${CSS.escape(menuKey)}"]`);
  if (relatedEditCheckbox && !viewCheckbox.checked) relatedEditCheckbox.checked = false;
  if (menuKey === "users") updatePermissionManagementScope(form);
});

const updatePermissionManagementScope = (form) => {
  if (!form) return;
  const scopeSection = form.querySelector("[data-permission-management-scope]");
  if (!scopeSection) return;
  const usersEditCheckbox = form.querySelector("[data-permission-edit='users']");
  const shouldShow = Boolean(usersEditCheckbox?.checked);
  const isReadOnly = scopeSection.dataset.permissionReadOnly === "true";
  scopeSection.hidden = !shouldShow;
  scopeSection.querySelectorAll("input, select, textarea, button").forEach((control) => {
    control.disabled = isReadOnly || !shouldShow;
  });
};

document.querySelectorAll("form").forEach(updatePermissionManagementScope);

const dateMaskSelector = "[data-date-mask], [data-interview-option-date], [data-reactivation-date]";

const dateMaskInputFromTarget = (target) => target?.closest?.(dateMaskSelector) || null;

const cleanDateSegment = (value, length) => String(value || "").replace(/\D/g, "").slice(0, length);

const formatInterviewOptionDateTyping = (value, { completeSegments = true } = {}) => {
  const raw = String(value || "");
  if (raw.includes("/")) {
    const parts = raw.split("/").slice(0, 3);
    const day = cleanDateSegment(parts[0], 2);
    const monthDigits = String(parts[1] || "").replace(/\D/g, "");
    const month = monthDigits.slice(0, 2);
    const year = `${monthDigits.slice(2)}${String(parts[2] || "").replace(/\D/g, "")}`.slice(0, 4);
    const hasFullDate = parts.length === 3 && year.length === 4;
    const shouldPadDay = completeSegments && day.length === 1 && (raw.includes("/") || hasFullDate);
    const shouldPadMonth = completeSegments && month.length === 1 && (parts.length === 3 || raw.endsWith("/") || hasFullDate);
    const formattedDay = shouldPadDay ? day.padStart(2, "0") : day;
    const formattedMonth = shouldPadMonth ? month.padStart(2, "0") : month;
    if (parts.length === 2 && monthDigits.length > 2) return `${formattedDay}/${formattedMonth}/${year}`.slice(0, 10);
    if (parts.length >= 3) return `${formattedDay}/${formattedMonth}/${year}`.slice(0, 10);
    if (parts.length === 2) return `${formattedDay}/${formattedMonth}${raw.endsWith("/") && formattedMonth ? "/" : ""}`.slice(0, 10);
    return formattedDay;
  }
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 1) return digits;
  if (digits.length === 2) return completeSegments ? `${digits}/` : digits;
  if (digits.length <= 3) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  if (digits.length === 4) return completeSegments ? `${digits.slice(0, 2)}/${digits.slice(2)}/` : `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
};

const normalizeInterviewOptionDate = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (raw.includes("/")) {
    const parts = raw.split("/").map((part) => part.replace(/\D/g, ""));
    if (parts.length === 3 && parts[2].length === 4) {
      return `${parts[0].padStart(2, "0").slice(-2)}/${parts[1].padStart(2, "0").slice(-2)}/${parts[2]}`;
    }
  }
  return formatInterviewOptionDateTyping(raw, { completeSegments: true });
};

const parseDdMmYyyyDate = (value) => {
  const match = String(value || "").trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const day = Number.parseInt(match[1], 10);
  const monthIndex = Number.parseInt(match[2], 10) - 1;
  const year = Number.parseInt(match[3], 10);
  const parsed = new Date(year, monthIndex, day);
  if (
    Number.isNaN(parsed.getTime()) ||
    parsed.getDate() !== day ||
    parsed.getMonth() !== monthIndex ||
    parsed.getFullYear() !== year
  ) {
    return null;
  }
  return parsed;
};

const isFutureDdMmYyyyDate = (value) => {
  const parsed = parseDdMmYyyyDate(value);
  if (!parsed) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return parsed >= today;
};

const easterSundayDate = (year) => {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(year, month - 1, day);
};

const addDays = (dateValue, days) => {
  const next = new Date(dateValue);
  next.setDate(next.getDate() + days);
  return next;
};

const dateKey = (dateValue) => {
  const year = dateValue.getFullYear();
  const month = String(dateValue.getMonth() + 1).padStart(2, "0");
  const day = String(dateValue.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const argentinaNationalHolidayKeys = (year) => {
  const easter = easterSundayDate(year);
  return new Set([
    `${year}-01-01`,
    dateKey(addDays(easter, -48)),
    dateKey(addDays(easter, -47)),
    `${year}-03-24`,
    dateKey(addDays(easter, -2)),
    `${year}-04-02`,
    `${year}-05-01`,
    `${year}-05-25`,
    `${year}-06-17`,
    `${year}-06-20`,
    `${year}-07-09`,
    `${year}-08-17`,
    `${year}-10-12`,
    `${year}-11-20`,
    `${year}-12-08`,
    `${year}-12-25`,
  ]);
};

const isArgentinaBusinessDate = (dateValue) => {
  if (!dateValue) return false;
  const day = dateValue.getDay();
  return day !== 0 && day !== 6 && !argentinaNationalHolidayKeys(dateValue.getFullYear()).has(dateKey(dateValue));
};

const nonBusinessPaymentDateMessage = "Payments cannot be processed on Saturdays, Sundays or public holidays.";

const dateMaskValidationMessage = (value, { futureOrToday = false, businessDate = false } = {}) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const match = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return "Please enter a valid date.";
  const day = Number.parseInt(match[1], 10);
  const month = Number.parseInt(match[2], 10);
  const year = Number.parseInt(match[3], 10);
  const currentYear = new Date().getFullYear();
  if (day < 1 || day > 31) return "Day must be between 01 and 31.";
  if (month < 1 || month > 12) return "Month must be between 01 and 12.";
  if (year < currentYear) return "Year must be the current year or later.";
  const parsed = parseDdMmYyyyDate(raw);
  if (!parsed) return "Please enter a valid date.";
  if (futureOrToday && !isFutureDdMmYyyyDate(raw)) return "Date cannot be in the past.";
  if (businessDate && !isArgentinaBusinessDate(parsed)) return nonBusinessPaymentDateMessage;
  return "";
};

const validateDateMaskInput = (input) => {
  if (!input?.setCustomValidity) return;
  const message = dateMaskValidationMessage(input.value, {
    futureOrToday: input.matches("[data-date-future-or-today]"),
    businessDate: input.matches("[data-finance-business-date]"),
  });
  input.setCustomValidity(message);
  const warning = input.closest("[data-finance-specific-payment-date]")?.querySelector("[data-finance-business-date-warning]");
  if (warning) warning.hidden = message !== nonBusinessPaymentDateMessage;
};

const formatDateMaskSlashInput = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const parts = raw.split("/").slice(0, 3);
  const day = cleanDateSegment(parts[0], 2);
  if (!raw.includes("/")) {
    return day ? `${day.padStart(2, "0")}/` : "";
  }
  const monthDigits = String(parts[1] || "").replace(/\D/g, "");
  const month = monthDigits.slice(0, 2);
  const year = `${monthDigits.slice(2)}${String(parts[2] || "").replace(/\D/g, "")}`.slice(0, 4);
  const formattedDay = day ? day.padStart(2, "0") : "";
  if (parts.length === 2) {
    if (!month) return formattedDay ? `${formattedDay}/` : "";
    return `${formattedDay}/${month.padStart(2, "0")}/${year}`.slice(0, 10);
  }
  return formatInterviewOptionDateTyping(raw, { completeSegments: true });
};

const completeCurrentDateMaskSegment = (input) => {
  if (!input) return;
  input.value = formatInterviewOptionDateTyping(input.value, { completeSegments: true });
  validateDateMaskInput(input);
};

const advanceDateMaskSegment = (input) => {
  if (!input) return;
  input.value = formatDateMaskSlashInput(input.value);
  if (typeof input.setSelectionRange === "function") {
    const cursorPosition = input.value.length;
    input.setSelectionRange(cursorPosition, cursorPosition);
  }
  validateDateMaskInput(input);
};

const timeMaskSelector = "[data-time-mask], [data-interview-option-time]";

const timeMaskInputFromTarget = (target) => target?.closest?.(timeMaskSelector) || null;

const formatInterviewOptionTimeTyping = (value) => {
  const raw = String(value || "").replace(/h\.?/gi, "").trim();
  if (raw.includes(":")) {
    const parts = raw.split(":").slice(0, 2);
    const hourDigits = String(parts[0] || "").replace(/\D/g, "");
    const minuteDigits = String(parts[1] || "").replace(/\D/g, "");
    const hours = hourDigits.slice(0, 2);
    const minutes = `${hourDigits.slice(2)}${minuteDigits}`.slice(0, 2);
    return `${hours}:${minutes}`.slice(0, 5);
  }
  const digits = raw.replace(/\D/g, "").slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}:${digits.slice(2)}`;
};

const normalizeInterviewOptionTime = (value) => {
  const raw = String(value || "").replace(/h\.?/gi, "").trim();
  if (!raw) return "";
  const digits = raw.replace(/\D/g, "");
  if (raw.includes(":")) {
    const [hours = "", minutes = ""] = raw.split(":");
    const cleanHours = hours.replace(/\D/g, "");
    const cleanMinutes = minutes.replace(/\D/g, "");
    if (cleanHours && cleanMinutes) return `${cleanHours.padStart(2, "0").slice(-2)}:${cleanMinutes.padStart(2, "0").slice(0, 2)}`;
    if (cleanHours) return `${cleanHours.padStart(2, "0").slice(-2)}:00`;
    return formatInterviewOptionTimeTyping(raw);
  }
  if (digits.length === 1 || digits.length === 2) return `${digits.padStart(2, "0")}:00`;
  if (digits.length === 3) return `${digits.slice(0, 1).padStart(2, "0")}:${digits.slice(1)}`;
  if (digits.length === 4) return `${digits.slice(0, 2)}:${digits.slice(2)}`;
  return formatInterviewOptionTimeTyping(raw);
};

const formatTimeColonInput = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (!raw.includes(":")) {
    const hours = raw.replace(/\D/g, "").slice(0, 2);
    return hours ? `${hours.padStart(2, "0")}:` : "";
  }
  const [hours = "", minutes = ""] = raw.split(":");
  const cleanHours = hours.replace(/\D/g, "").slice(0, 2);
  const cleanMinutes = minutes.replace(/\D/g, "").slice(0, 2);
  if (!cleanHours) return "";
  return `${cleanHours.padStart(2, "0")}:${cleanMinutes.padStart(2, "0")}`.slice(0, 5);
};

const parseTimeMaskValue = (value) => {
  const match = String(value || "").trim().match(/^(\d{2}):(\d{2})$/);
  if (!match) return null;
  const hours = Number.parseInt(match[1], 10);
  const minutes = Number.parseInt(match[2], 10);
  if (hours < 0 || hours > 24 || minutes < 0 || minutes > 60) return null;
  return (hours * 60) + minutes;
};

const timeMaskValidationMessage = (input) => {
  const raw = String(input?.value || "").trim();
  if (!raw) return "";
  const minutes = parseTimeMaskValue(raw);
  if (minutes === null) return "Please enter a valid 24-hour time.";
  const row = input.closest?.("[data-induction-option-row]");
  if (!row) return "";
  const startInput = row.querySelector("[data-induction-option-start-time]");
  const endInput = row.querySelector("[data-induction-option-end-time]");
  const startMinutes = parseTimeMaskValue(startInput?.value);
  const endMinutes = parseTimeMaskValue(endInput?.value);
  if (startMinutes === null || endMinutes === null) return "";
  if (startMinutes >= endMinutes) {
    return input.matches("[data-induction-option-start-time]")
      ? "Start time must be earlier than end time."
      : "End time must be later than start time.";
  }
  return "";
};

const validateInductionTimeRange = (row) => {
  row?.querySelectorAll?.("[data-induction-option-start-time], [data-induction-option-end-time]").forEach((input) => {
    if (input.setCustomValidity) input.setCustomValidity(timeMaskValidationMessage(input));
  });
};

const validateTimeMaskInput = (input) => {
  if (!input?.setCustomValidity) return;
  input.setCustomValidity(timeMaskValidationMessage(input));
  validateInductionTimeRange(input.closest?.("[data-induction-option-row]"));
};

const completeTimeMaskInput = (input) => {
  if (!input) return;
  input.value = normalizeInterviewOptionTime(input.value);
  validateTimeMaskInput(input);
};

const advanceTimeMaskSegment = (input) => {
  if (!input) return;
  input.value = formatTimeColonInput(input.value);
  if (typeof input.setSelectionRange === "function") {
    const cursorPosition = input.value.length;
    input.setSelectionRange(cursorPosition, cursorPosition);
  }
  validateTimeMaskInput(input);
};

const focusNextTimeMaskInput = (input) => {
  const row = input?.closest?.("[data-induction-option-row]");
  const scope = row || input?.closest?.("form");
  if (!scope) return;
  const fields = Array.from(scope.querySelectorAll("[data-time-mask], [data-interview-option-time]"))
    .filter((field) => !field.disabled && field.offsetParent !== null);
  const currentIndex = fields.indexOf(input);
  const nextField = currentIndex >= 0 ? fields[currentIndex + 1] : null;
  nextField?.focus();
};

const syncProceedInterviewButton = (element) => {
  const form = element?.closest?.("form") || element?.querySelector?.("form") || element;
  window.syncPotentialProceedInterviewButton?.(form);
};

const scheduleProceedInterviewButtonSync = (element) => {
  const form = element?.closest?.("form") || element?.querySelector?.("form") || element;
  if (!form?.querySelector?.("[data-proceed-interview-button]")) return;
  window.requestAnimationFrame(() => syncProceedInterviewButton(form));
};

const interviewOptionsListForRoot = (root) => root?.querySelector("[data-interview-options-list]");

const interviewOptionRowsForRoot = (root) => {
  const list = interviewOptionsListForRoot(root);
  if (!list) return [];
  return Array.from(list.children).filter((child) => child.matches?.("[data-interview-option-row]"));
};

const syncInterviewOptionControls = (root) => {
  if (!root) return;
  const maxOptions = Number(root.dataset.maxOptions || 5);
  const rows = interviewOptionRowsForRoot(root);
  const addButton = root.querySelector("[data-add-interview-option]");
  if (addButton) addButton.disabled = rows.length >= maxOptions;
  rows.forEach((row, index) => {
    const removeButton = row.querySelector("[data-remove-interview-option]");
    if (removeButton) {
      removeButton.hidden = index === 0;
      removeButton.disabled = false;
    }
  });
  syncProceedInterviewButton(root.closest("form"));
};

const addInterviewOptionRow = (addButton) => {
  const root = addButton?.closest?.("[data-interview-options-root]");
  const list = interviewOptionsListForRoot(root);
  const rows = interviewOptionRowsForRoot(root);
  const maxOptions = Number(root?.dataset.maxOptions || 5);
  if (!root || !list || !rows.length || rows.length >= maxOptions) return false;
  const clone = rows[rows.length - 1].cloneNode(true);
  clone.classList.add("is-extra");
  clone.querySelectorAll("input").forEach((input) => {
    input.value = "";
    input.disabled = false;
  });
  clone.querySelectorAll("select").forEach((select) => {
    select.value = "";
    select.disabled = false;
    if (select.matches("[data-interview-option-platform]")) syncInterviewOptionPlatformPreview(select);
  });
  clone.querySelectorAll("button").forEach((button) => {
    button.disabled = false;
  });
  list.insertBefore(clone, addButton);
  syncInterviewOptionControls(root);
  clone.scrollIntoView?.({ block: "nearest" });
  clone.querySelector("input")?.focus();
  return true;
};

const removeInterviewOptionRow = (removeButton) => {
  const root = removeButton?.closest?.("[data-interview-options-root]");
  const row = removeButton?.closest?.("[data-interview-option-row]");
  const rows = interviewOptionRowsForRoot(root);
  if (!root || !row) return false;
  if (rows.length <= 1) {
    row.querySelectorAll("input").forEach((input) => {
      input.value = "";
    });
  } else {
    row.remove();
  }
  syncInterviewOptionControls(root);
  return true;
};

const initInterviewOptionsRoot = (root) => {
  if (!root || root.dataset.interviewOptionsInitialized === "true") return;
  root.dataset.interviewOptionsInitialized = "true";
  syncInterviewOptionControls(root);
  root.addEventListener("click", (event) => {
    const addButton = event.target.closest?.("[data-add-interview-option]");
    if (addButton) {
      event.preventDefault();
      event.stopPropagation();
      addInterviewOptionRow(addButton);
      return;
    }
    const removeButton = event.target.closest?.("[data-remove-interview-option]");
    if (removeButton) {
      event.preventDefault();
      event.stopPropagation();
      removeInterviewOptionRow(removeButton);
    }
  });
};

const platformPreviewHtml = (platform) => {
  if (platform === "Zoom") return '<img class="platform-logo-img" src="/static/img/zoom.png" alt="Zoom" title="Zoom"><span>Zoom</span>';
  if (platform === "Meet") return '<img class="platform-logo-img platform-logo-meet" src="/static/img/google-meet.png" alt="Google Meet" title="Google Meet"><span>Meet</span>';
  return "";
};

const syncInterviewOptionPlatformPreview = (select) => {
  const root = select?.closest("[data-interview-options-root]") || select?.closest(".onboarding-induction-group") || select?.closest("form");
  const preview = root?.querySelector("[data-interview-option-platform-preview]");
  if (preview) {
    preview.innerHTML = platformPreviewHtml(select.value);
    preview.hidden = !select.value;
  }
};

document.querySelectorAll("[data-interview-options-root]").forEach(initInterviewOptionsRoot);
document.querySelectorAll("[data-interview-option-platform]").forEach(syncInterviewOptionPlatformPreview);
document.querySelectorAll("[data-proceed-interview-button]").forEach((button) => {
  syncProceedInterviewButton(button.closest("form"));
});

const syncPotentialInterviewNoShow = (element) => {
  const form = element?.closest?.("form") || element?.querySelector?.("form") || element;
  const checkbox = form?.querySelector?.("[data-interview-no-show]");
  if (!form || !checkbox) return;
  if (checkbox.disabled) return;
  const isNoShow = checkbox.checked;
  form.querySelectorAll("[data-no-show-disabled-group]").forEach((group) => {
    group.disabled = isNoShow;
    group.querySelectorAll("input, select, textarea, button").forEach((control) => {
      control.disabled = isNoShow;
    });
  });
  const acceptedButton = form.querySelector("[data-application-accepted-button]");
  const acceptedOnHoldButton = form.querySelector("[data-application-accepted-on-hold-button]");
  const hasCar = Boolean(form.querySelector("input[name='interview_has_car']:checked"));
  const hasRole = Boolean(form.querySelector("input[name='interview_roles']:checked"));
  const outcome = form.querySelector("input[name='entry_acceptance_outcome']:checked")?.value || "";
  const acceptanceChecksContainer = form.querySelector("[data-interview-acceptance-checks]");
  if (acceptanceChecksContainer) {
    acceptanceChecksContainer.hidden = outcome !== "sessions_pre_confirmation";
    if (outcome !== "sessions_pre_confirmation") {
      acceptanceChecksContainer.querySelectorAll("[data-interview-acceptance-required]").forEach((field) => {
        field.checked = false;
      });
    }
  }
  const acceptanceChecksComplete = outcome !== "sessions_pre_confirmation" || Array.from(form.querySelectorAll("[data-interview-acceptance-required]")).every((field) => field.checked);
  const reactivationDate = form.querySelector("[data-reactivation-date]")?.value || "";
  const canAccept = Boolean(!isNoShow && hasCar && hasRole && outcome === "sessions_pre_confirmation" && acceptanceChecksComplete);
  const canAcceptOnHold = Boolean(!isNoShow && hasCar && hasRole && outcome === "on_hold" && isFutureDdMmYyyyDate(reactivationDate));
  if (acceptedButton) {
    acceptedButton.disabled = !canAccept;
    if (canAccept) acceptedButton.removeAttribute("title");
    else acceptedButton.setAttribute("title", isNoShow ? "No-show entries cannot be accepted." : "Complete Has a car, Roles, session pre-confirmation, and confirmation before accepting.");
  }
  if (acceptedOnHoldButton) {
    acceptedOnHoldButton.disabled = !canAcceptOnHold;
    if (canAcceptOnHold) acceptedOnHoldButton.removeAttribute("title");
    else acceptedOnHoldButton.setAttribute("title", isNoShow ? "No-show entries cannot be accepted." : "Complete Has a car, Roles, on-hold selection, and a future reactivation date.");
  }
};

document.querySelectorAll("[data-interview-no-show]").forEach((checkbox) => {
  syncPotentialInterviewNoShow(checkbox.closest("form"));
});

const syncInterviewInvitationConfirmation = (element) => {
  const form = element?.closest?.("form") || element?.querySelector?.("form") || element;
  if (window.syncPotentialInterviewInvitationActions) {
    window.syncPotentialInterviewInvitationActions(form);
    return;
  }
  const root = form?.querySelector?.("[data-interview-confirm-root]");
  if (!form || !root) return;
  const noReply = Boolean(root.querySelector("[data-interview-no-reply]")?.checked);
  const selectedOption = root.querySelector("[data-interview-option-choice]:checked");
  root.querySelectorAll("[data-interview-option-choice]").forEach((option) => {
    option.disabled = noReply;
    if (noReply) option.checked = false;
  });
  const hasSelectedOption = Boolean(!noReply && selectedOption);
  const confirmButton = form.querySelector("[data-interview-confirm-button]");
  const turnDownButton = form.querySelector("[data-interview-turn-down-button]");
  const reviewButton = form.querySelector("[data-review-date-time-options-button]");
  if (confirmButton) {
    confirmButton.disabled = !hasSelectedOption;
    confirmButton.setAttribute("title", hasSelectedOption ? "" : "Select one date/time option before confirming the interview.");
    if (hasSelectedOption) confirmButton.removeAttribute("title");
  }
  if (turnDownButton) {
    turnDownButton.disabled = !noReply;
    turnDownButton.setAttribute("title", noReply ? "" : "Select No reply before turning down the application.");
    if (noReply) turnDownButton.removeAttribute("title");
  }
  if (reviewButton) {
    const canReview = !noReply && !hasSelectedOption;
    reviewButton.disabled = !canReview;
    reviewButton.setAttribute("title", canReview ? "" : "Clear No reply and date/time selection to review options.");
    if (canReview) reviewButton.removeAttribute("title");
  }
};

document.querySelectorAll("[data-interview-confirm-root]").forEach((root) => {
  syncInterviewInvitationConfirmation(root.closest("form"));
});

const syncEntryAcceptedOnboardingButton = (element) => {
  const form = element?.closest?.("form") || element?.querySelector?.("form") || element;
  if (window.syncPotentialEntryAcceptedOnboardingButton) {
    window.syncPotentialEntryAcceptedOnboardingButton(form);
    return;
  }
  const button = form?.querySelector?.("[data-onboarding-email-sent-button]");
  if (!form || !button) return;
  const requiredNames = [
    "entry_accepted_notes_checked",
    "entry_accepted_email_sent",
    "entry_accepted_whatsapp_sent",
    "entry_accepted_pre_confirmation_sent",
  ];
  const canMarkSent = requiredNames.every((name) => form.querySelector(`input[name="${name}"]`)?.checked);
  button.disabled = !canMarkSent;
  if (canMarkSent) {
    button.removeAttribute("title");
  } else {
    button.setAttribute("title", "Complete all four checks before marking onboarding email as sent.");
  }
};

document.querySelectorAll("[data-onboarding-email-sent-button]").forEach((button) => {
  syncEntryAcceptedOnboardingButton(button.closest("form"));
});

const syncOnboardingFollowUpControls = (element) => {
  const form = element?.closest?.("form") || element?.querySelector?.("form") || element;
  if (window.syncPotentialOnboardingFollowUpControls) {
    window.syncPotentialOnboardingFollowUpControls(form);
    return;
  }
  const root = form?.querySelector?.("[data-onboarding-follow-up]");
  if (!form || !root) return;
  root.querySelectorAll("[data-interview-option-platform]").forEach(syncInterviewOptionPlatformPreview);
  const choice = root.querySelector("[data-onboarding-choice]:checked")?.value || "";
  root.querySelectorAll("[data-onboarding-panel]").forEach((panel) => {
    const key = panel.dataset.onboardingPanel;
    panel.classList.toggle("is-active", key === choice);
  });
  root.querySelectorAll("[data-onboarding-fieldset]").forEach((fieldset) => {
    fieldset.disabled = fieldset.dataset.onboardingFieldset !== choice;
  });
	  const confirmComplete = Boolean(choice === "confirm") && Array.from(root.querySelectorAll("[data-onboarding-confirm-required]")).every((field) => {
	    if (field.disabled) return false;
	    if (field.type === "checkbox") return field.checked;
	    return Boolean(field.value?.trim());
	  });
  const turnDownComplete = Boolean(choice === "turn_down") && Array.from(root.querySelectorAll("[data-onboarding-turn-down-required]")).every((field) => (
    !field.disabled && field.checked
  ));
  const confirmButton = form.querySelector("[data-onboarding-confirm-button]");
  const turnDownButton = form.querySelector("[data-onboarding-turn-down-button]");
  if (confirmButton) {
    confirmButton.disabled = !confirmComplete;
    confirmButton.setAttribute("title", confirmComplete ? "" : "Complete all required confirm application fields.");
    if (confirmComplete) confirmButton.removeAttribute("title");
  }
  if (turnDownButton) {
    turnDownButton.disabled = !turnDownComplete;
    turnDownButton.setAttribute("title", turnDownComplete ? "" : "Complete both turn down application checks.");
    if (turnDownComplete) turnDownButton.removeAttribute("title");
  }
};

document.querySelectorAll("[data-onboarding-follow-up]").forEach((root) => {
  syncOnboardingFollowUpControls(root.closest("form"));
});

const syncInductionStatusPanels = (element) => {
  const root = element?.closest?.("[data-induction-status-root]") || element;
  if (window.syncPotentialOutcomeStatusPanels) {
    window.syncPotentialOutcomeStatusPanels(root);
    return;
  }
  if (!root) return;
  const form = root.closest("form");
  const selected = root.querySelector("[data-induction-status-option]:checked")?.value || "";
  root.querySelectorAll("[data-induction-status-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.inductionStatusPanel !== selected;
  });
  const rescheduleComplete = selected === "reschedule" && Array.from(root.querySelectorAll("[data-induction-reschedule-required]")).every((field) => {
    if (field.disabled) return false;
    if (field.type === "checkbox") return field.checked;
    return Boolean(field.value?.trim());
  });
  const noShowCheck = root.querySelector("[data-induction-no-show-required]");
  const noShowComplete = selected === "no_show" && (!noShowCheck || noShowCheck.checked);
  const attendedComplete = selected === "attended";
  const acceptanceOutcome = root.querySelector("input[name='entry_acceptance_outcome']:checked")?.value || "";
  const reactivationDateField = root.querySelector("[data-reactivation-date-field]");
  const reactivationDateInput = root.querySelector("[data-reactivation-date]");
  if (reactivationDateField) reactivationDateField.hidden = acceptanceOutcome !== "on_hold";
  const acceptanceChecksContainer = form?.querySelector("[data-interview-acceptance-checks]");
  if (acceptanceChecksContainer) {
    acceptanceChecksContainer.hidden = acceptanceOutcome !== "sessions_pre_confirmation";
    if (acceptanceOutcome !== "sessions_pre_confirmation") {
      acceptanceChecksContainer.querySelectorAll("[data-interview-acceptance-required]").forEach((field) => {
        field.checked = false;
      });
    }
  }
  const acceptanceChecksComplete = acceptanceOutcome !== "sessions_pre_confirmation" || Array.from(form?.querySelectorAll("[data-interview-acceptance-required]") || []).every((field) => field.checked);
  const interviewAttendedComplete = selected === "attended"
    && Boolean(root.querySelector("input[name='interview_has_car']:checked"))
    && Boolean(root.querySelector("input[name='interview_roles']:checked"))
    && acceptanceOutcome === "sessions_pre_confirmation"
    && acceptanceChecksComplete;
  const interviewOnHoldComplete = selected === "attended"
    && Boolean(root.querySelector("input[name='interview_has_car']:checked"))
    && Boolean(root.querySelector("input[name='interview_roles']:checked"))
    && acceptanceOutcome === "on_hold"
    && isFutureDdMmYyyyDate(reactivationDateInput?.value || "");
  const rejectButton = form?.querySelector("[data-induction-reject-button]");
  const rescheduleButton = form?.querySelector("[data-induction-reschedule-button]");
  const activateButton = form?.querySelector("[data-induction-activate-button]");
  const acceptedButton = form?.querySelector("[data-application-accepted-button]");
  const acceptedOnHoldButton = form?.querySelector("[data-application-accepted-on-hold-button]");
  const interviewPreassigned = form?.querySelector("[data-interview-preassigned-readonly]");
  if (interviewPreassigned) interviewPreassigned.hidden = selected !== "attended";
  if (rejectButton) rejectButton.disabled = !noShowComplete;
  if (rescheduleButton) rescheduleButton.disabled = !rescheduleComplete;
  if (activateButton) activateButton.disabled = !attendedComplete;
  if (acceptedButton) acceptedButton.disabled = !interviewAttendedComplete;
  if (acceptedOnHoldButton) acceptedOnHoldButton.disabled = !interviewOnHoldComplete;
};

document.querySelectorAll("[data-induction-status-root]").forEach(syncInductionStatusPanels);

const syncEntryAcceptedCheck = async (checkbox) => {
  const action = checkbox?.dataset.action;
  if (!action) return;
  const root = checkbox.closest("[data-entry-accepted-email-root]");
  const status = root?.querySelector("[data-entry-accepted-email-status]");
	  const formData = new FormData();
	  formData.set("csrf_token", document.querySelector("input[name='csrf_token']")?.value || "");
	  formData.set(checkbox.name, checkbox.checked ? "1" : "0");
	  try {
    const response = await fetch(action, {
      method: "POST",
      body: formData,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.error) throw new Error(payload.error || "Could not save checkbox.");
    syncEntryAcceptedOnboardingButton(checkbox.closest("form"));
    if (status) {
      status.textContent = "Notes check saved.";
      status.classList.remove("is-error");
      window.setTimeout(() => {
        status.textContent = "";
      }, 1400);
    }
  } catch (error) {
    checkbox.checked = !checkbox.checked;
    syncEntryAcceptedOnboardingButton(checkbox.closest("form"));
    if (status) {
      status.textContent = error.message || "Could not save checkbox.";
      status.classList.add("is-error");
      window.setTimeout(() => {
        status.textContent = "";
        status.classList.remove("is-error");
      }, 2400);
    }
	  } finally {
	    syncEntryAcceptedOnboardingButton(checkbox.closest("form"));
	  }
	};

document.addEventListener("input", (event) => {
  const onboardingField = event.target.closest("[data-onboarding-confirm-required]");
  if (onboardingField) {
    syncOnboardingFollowUpControls(onboardingField.closest("form"));
  }
  const maskedDateInput = dateMaskInputFromTarget(event.target);
  if (maskedDateInput) {
    const isDeleting = String(event.inputType || "").startsWith("delete");
    maskedDateInput.value = formatInterviewOptionDateTyping(maskedDateInput.value, { completeSegments: !isDeleting });
    validateDateMaskInput(maskedDateInput);
    if (maskedDateInput.matches("[data-interview-option-date]")) {
      scheduleProceedInterviewButtonSync(maskedDateInput);
      syncInductionStatusPanels(maskedDateInput);
    } else if (maskedDateInput.matches("[data-reactivation-date]")) {
      syncInductionStatusPanels(maskedDateInput);
    }
    return;
  }
  const timeInput = timeMaskInputFromTarget(event.target);
  if (timeInput) {
    timeInput.value = formatInterviewOptionTimeTyping(timeInput.value);
    validateTimeMaskInput(timeInput);
    scheduleProceedInterviewButtonSync(timeInput);
    if (timeInput.matches("[data-interview-option-time]")) syncInductionStatusPanels(timeInput);
    return;
  }
  scheduleProceedInterviewButtonSync(event.target);
});

document.addEventListener("change", (event) => {
  const onboardingControl = event.target.closest("[data-onboarding-choice], [data-onboarding-confirm-required], [data-onboarding-turn-down-required]");
  if (onboardingControl) {
    syncOnboardingFollowUpControls(onboardingControl.closest("form"));
    return;
  }
  const entryAcceptedCheckbox = event.target.closest("[data-entry-accepted-check]");
  if (entryAcceptedCheckbox) {
    syncEntryAcceptedCheck(entryAcceptedCheckbox);
    return;
  }
  const noShowControl = event.target.closest("[data-interview-no-show]");
  if (noShowControl) {
    syncPotentialInterviewNoShow(noShowControl.closest("form"));
    return;
  }
  const interviewConfirmControl = event.target.closest("[data-interview-no-reply], [data-interview-option-choice]");
  if (interviewConfirmControl) {
    if (interviewConfirmControl.matches("[data-interview-option-choice]") && interviewConfirmControl.checked) {
      const root = interviewConfirmControl.closest("[data-interview-confirm-root]");
      const noReply = root?.querySelector("[data-interview-no-reply]");
      if (noReply) noReply.checked = false;
      root?.querySelectorAll("[data-interview-option-choice]").forEach((option) => {
        if (option !== interviewConfirmControl) option.checked = false;
      });
    }
    syncInterviewInvitationConfirmation(interviewConfirmControl.closest("form"));
    return;
  }
  const inductionStatusOption = event.target.closest("[data-induction-status-option], [data-induction-reschedule-required], [data-induction-no-show-required], [data-interview-acceptance-required], input[name='interview_has_car'], input[name='interview_roles'], input[name='entry_acceptance_outcome']");
  if (inductionStatusOption) {
    syncInductionStatusPanels(inductionStatusOption);
    return;
  }
  const platformSelect = event.target.closest("[data-interview-option-platform]");
  if (platformSelect) {
    syncInterviewOptionPlatformPreview(platformSelect);
    scheduleProceedInterviewButtonSync(platformSelect);
    return;
  }
  const interviewerSelect = event.target.closest("select[name='interview_option_interviewer']");
  if (interviewerSelect) {
    scheduleProceedInterviewButtonSync(interviewerSelect);
    return;
  }
  scheduleProceedInterviewButtonSync(event.target);
});

document.addEventListener("paste", (event) => {
  const field = event.target.closest("[data-interview-option-date], [data-interview-option-time]");
  if (field) scheduleProceedInterviewButtonSync(field);
});

document.addEventListener("blur", (event) => {
  const maskedDateInput = dateMaskInputFromTarget(event.target);
  if (maskedDateInput) {
    maskedDateInput.value = normalizeInterviewOptionDate(maskedDateInput.value);
    validateDateMaskInput(maskedDateInput);
    if (maskedDateInput.matches("[data-interview-option-date]")) {
      scheduleProceedInterviewButtonSync(maskedDateInput);
      syncInductionStatusPanels(maskedDateInput);
    } else if (maskedDateInput.matches("[data-reactivation-date]")) {
      syncInductionStatusPanels(maskedDateInput);
    }
    return;
  }
  const timeInput = timeMaskInputFromTarget(event.target);
  if (timeInput) {
    completeTimeMaskInput(timeInput);
    scheduleProceedInterviewButtonSync(timeInput);
    if (timeInput.matches("[data-interview-option-time]")) syncInductionStatusPanels(timeInput);
  }
}, true);

document.addEventListener("keydown", (event) => {
  const maskedDateInput = dateMaskInputFromTarget(event.target);
  if (maskedDateInput) {
    if (event.key === "/") {
      event.preventDefault();
      advanceDateMaskSegment(maskedDateInput);
      scheduleProceedInterviewButtonSync(maskedDateInput);
      return;
    }
    if (event.key === "Tab") {
      completeCurrentDateMaskSegment(maskedDateInput);
      scheduleProceedInterviewButtonSync(maskedDateInput);
    }
  }
  const timeInput = timeMaskInputFromTarget(event.target);
  if (!timeInput) return;
  if (event.key === "Shift") {
    timeInput.dataset.shiftTimeAdvance = "true";
    return;
  }
  if (event.shiftKey && event.key !== "Shift") {
    delete timeInput.dataset.shiftTimeAdvance;
  }
  if (event.key === ":") {
    event.preventDefault();
    advanceTimeMaskSegment(timeInput);
    scheduleProceedInterviewButtonSync(timeInput);
    return;
  }
  if (event.key === "Tab") {
    completeTimeMaskInput(timeInput);
    scheduleProceedInterviewButtonSync(timeInput);
  }
});

document.addEventListener("keyup", (event) => {
  if (event.key !== "Shift") return;
  const dateInput = dateMaskInputFromTarget(event.target);
  completeCurrentDateMaskSegment(dateInput);
  scheduleProceedInterviewButtonSync(dateInput);
  const timeInput = timeMaskInputFromTarget(event.target);
  if (!timeInput) return;
  const shouldAdvance = timeInput.dataset.shiftTimeAdvance === "true";
  delete timeInput.dataset.shiftTimeAdvance;
  completeTimeMaskInput(timeInput);
  scheduleProceedInterviewButtonSync(timeInput);
  if (shouldAdvance) focusNextTimeMaskInput(timeInput);
});

document.addEventListener("click", (event) => {
  const addButton = event.target.closest("[data-add-interview-option]");
  if (addButton) {
    event.preventDefault();
    addInterviewOptionRow(addButton);
    return;
  }

  const removeButton = event.target.closest("[data-remove-interview-option]");
  if (removeButton) {
    event.preventDefault();
    removeInterviewOptionRow(removeButton);
  }
});

const syncShipmentDeliveryOptions = (fieldset) => {
  if (!fieldset) return;
  const inputs = Array.from(fieldset.querySelectorAll("input[name='delivery_option']"));
  const selected = inputs.find((input) => input.checked);
  if (fieldset.dataset.shipmentDeliverySelectedValue === undefined) {
    fieldset.dataset.shipmentDeliverySelectedValue = selected?.value || "";
  }
  const fieldsetDisabled = fieldset.disabled || fieldset.hasAttribute("disabled");
  inputs.forEach((input) => {
    if (!fieldsetDisabled) {
      input.disabled = false;
    }
    input.closest("label")?.classList.toggle("is-disabled", fieldsetDisabled || input.disabled);
  });
};

document.querySelectorAll(".shipment-delivery-options").forEach(syncShipmentDeliveryOptions);

document.addEventListener("change", (event) => {
  const input = event.target.closest?.(".shipment-delivery-options input[name='delivery_option']");
  if (!input) return;
  const fieldset = input.closest(".shipment-delivery-options");
  const form = fieldset?.closest("form");
  const previousValue = fieldset?.dataset.shipmentDeliverySelectedValue || "";
  const nextValue = input.checked ? input.value : "";
  if (fieldset?.dataset.shipmentDeliveryAutoSave === "true" && form?.dataset.confirmPasswordSubmit && nextValue !== previousValue) {
    const message = form.dataset.confirmPasswordSubmit || "This action cannot be undone.";
    const expectedPassword = form.dataset.confirmPasswordValue || "Path1234";
    const password = window.prompt(`${message}\n\nEnter the confirmation password to continue:`);
    if (password === null) {
      fieldset.querySelectorAll("input[name='delivery_option']").forEach((option) => {
        option.checked = option.value === previousValue;
      });
      syncShipmentDeliveryOptions(fieldset);
      return;
    }
    if (password !== expectedPassword) {
      window.alert("Incorrect password. The action was cancelled.");
      fieldset.querySelectorAll("input[name='delivery_option']").forEach((option) => {
        option.checked = option.value === previousValue;
      });
      syncShipmentDeliveryOptions(fieldset);
      return;
    }
    const confirmationPasswordInput = form.querySelector("input[name='confirmation_password']");
    if (confirmationPasswordInput) confirmationPasswordInput.value = password;
  }
  if (input.checked) {
    fieldset?.querySelectorAll("input[name='delivery_option']").forEach((option) => {
      if (option !== input) option.checked = false;
    });
  }
  syncShipmentDeliveryOptions(fieldset);
  if (fieldset?.dataset.shipmentDeliveryAutoSave === "true") {
    if (form?.requestSubmit) {
      form.requestSubmit();
    } else {
      form?.submit();
    }
  }
});

const applyViewOnlyMode = () => {
  const main = document.querySelector("main[data-current-menu-can-edit='false']");
  if (!main) return;
  const viewOnlyTitle = "Edit permission required";
  const mutatingButtonPattern = /^(new|add|create|edit|save|save and close|delete|remove|archive|unarchive|reset|import|apply|confirm|complete|mark|generate|regenerate|disable|enable|duplicate|restore|send email|copy|ok)$/i;
  const mutatingTargetPattern = /(^|[-_])(create|edit|delete|archive|reset|import|confirm|generate|regenerate|disable|enable|copy|email|journey|payment|invoice|status|mark)([-_]|$)/i;
  const disableControl = (element) => {
    if (!element || element.dataset.viewOnlyAllowed === "true") return;
    element.classList.add("view-only-disabled");
    element.setAttribute("aria-disabled", "true");
    element.setAttribute("title", viewOnlyTitle);
    if ("disabled" in element) element.disabled = true;
    if (element.tagName === "A") element.setAttribute("tabindex", "-1");
  };

  main.querySelectorAll(".modal-panel").forEach((panel) => {
    if (panel.querySelector(".modal-view-only-banner")) return;
    const banner = document.createElement("section");
    banner.className = "modal-view-only-banner";
    banner.innerHTML = "<h3>View-only access</h3><p>Your account can view this information, but does not have permission to edit it.</p>";
    const header = panel.querySelector(".modal-header");
    if (header) header.insertAdjacentElement("afterend", banner);
    else panel.prepend(banner);
  });

  main.querySelectorAll("form[method='post' i]").forEach((form) => {
    form.querySelectorAll("input:not([type='hidden']), select, textarea, button, [role='button']").forEach(disableControl);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
    }, true);
  });

  main.querySelectorAll(".modal input:not([type='hidden']), .modal select, .modal textarea").forEach((field) => {
    field.disabled = true;
    field.classList.add("view-only-disabled");
  });

  main.querySelectorAll("button, a, summary, [role='button']").forEach((element) => {
    const text = (element.textContent || element.getAttribute("aria-label") || element.getAttribute("title") || "").trim();
    const target = [
      element.dataset.openModal,
      element.dataset.copyText,
      element.dataset.copyInvitationEmail,
      element.getAttribute("href"),
      element.getAttribute("data-action"),
      element.className || "",
    ].filter(Boolean).join(" ");
    if (
      element.matches(".copy-icon-button, [data-copy-text], [data-copy-invitation-email], [data-staff-address-copy], [data-copy-journey-link], [data-bulk-email-link], [data-acceptance-draft-save], [data-delete-logistics-concept], [data-remove-supervisor-row], [data-staff-declined-button], [data-emergency-contact-declined-button], [data-add-time-range], [data-remove-time-range], [data-disable-km], [data-edit-assignment-fees], [data-clear-selection], [data-provider-type-create-form] button") ||
      mutatingButtonPattern.test(text) ||
      mutatingTargetPattern.test(target)
    ) {
      disableControl(element);
    }
  });
};

applyViewOnlyMode();

document.addEventListener("click", (event) => {
  const disabledViewOnlyControl = event.target.closest?.(".view-only-disabled[aria-disabled='true']");
  if (!disabledViewOnlyControl) return;
  event.preventDefault();
  event.stopImmediatePropagation();
}, true);
