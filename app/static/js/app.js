const modalOpeners = new WeakMap();

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
  if (focus) {
    window.requestAnimationFrame(() => focusModalHeading(modal));
  }
};

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
  staffing: "Staffing",
  logistics: "Logistics",
  packages: "Packages",
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
  "schedule-overview": ["schedule-overview", "schedule-actions"],
  readiness: ["readiness", "session-readiness"],
  "session-readiness": ["readiness", "session-readiness"],
  incidents: ["incidents"],
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

const clearFocusedMode = (modal) => {
  if (!modal) return;
  modal.classList.remove("is-focused-mode");
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

const focusModalTarget = (targetId) => {
  const target = resolveModalTarget(targetId);
  if (!target) return false;
  const section = target.closest("[data-control-section]");
  expandControlSection(section);
  target.scrollIntoView({ block: "start", behavior: "smooth" });
  target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: true });
  highlightModalTarget(target);
  return true;
};

const closeModal = (modal) => {
  modal.classList.remove("is-open");
  modal.setAttribute("aria-hidden", "true");
  clearFocusedMode(modal);
  resetControlSectionsToDefault(modal);
  const opener = modalOpeners.get(modal);
  if (opener && document.contains(opener)) opener.focus();
};

const openRequestedSessionModal = () => {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("open_session_modal");
  if (!sessionId) return;
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
  if (actionKey) {
    const form = document.querySelector(`#schedule-workflow-${sessionId} [data-schedule-action-panel][data-schedule-action-key="${CSS.escape(actionKey)}"]`);
    const trigger = document.querySelector(`#schedule-workflow-${sessionId} [data-schedule-action-toggle][aria-controls="${form?.id || ""}"]`);
    if (form) {
      openScheduleActionPanel(form, trigger, { focus: false });
      const flash = document.querySelector(".flash.error");
      const errorBox = form.querySelector("[data-schedule-action-error]");
      if (flash && errorBox) {
        errorBox.textContent = flash.textContent.trim();
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
        errorBox.textContent = flash.textContent.trim();
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
        errorBox.textContent = flash.textContent.trim();
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
        errorBox.textContent = flash.textContent.trim();
        errorBox.hidden = false;
      }
    }
  }
  if (params.get("open_sinapsis_control") === "1") {
    const form = document.querySelector(`#schedule-workflow-${sessionId} [data-sinapsis-control-form]`);
    const trigger = document.querySelector(`#schedule-workflow-${sessionId} [data-sinapsis-control-toggle]`);
    if (form) {
      openSinapsisControlForm(form, trigger, { focus: false });
      const flash = document.querySelector(".flash.error");
      const errorBox = form.querySelector("[data-sinapsis-control-error]");
      if (flash && errorBox) {
        errorBox.textContent = flash.textContent.trim();
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
        errorBox.textContent = flash.textContent.trim();
        errorBox.hidden = false;
      }
    }
  }
  params.delete("open_schedule_modal");
  params.delete("open_modal_target");
  params.delete("open_schedule_action");
  params.delete("open_staffing_control");
  params.delete("open_logistics_control");
  params.delete("open_finance_control");
  params.delete("open_sinapsis_control");
  params.delete("open_communications_control");
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", nextUrl);
  if (modalTarget) {
    window.requestAnimationFrame(() => {
      const modal = document.getElementById(`schedule-workflow-${sessionId}`);
      const targetId = `${modalTarget}-${sessionId}`;
      setFocusedMode(modal, targetId);
      if (!focusModalTarget(targetId)) {
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
  params.delete("open_staff_modal");
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", nextUrl);
};

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
  modal?.querySelectorAll("[data-sinapsis-control-form]").forEach((panel) => {
    closeSinapsisControlForm(panel, { restoreFocus: false });
  });
  modal?.querySelectorAll("[data-communications-control-form]").forEach((panel) => {
    closeCommunicationsControlForm(panel, { restoreFocus: false });
  });
  form.hidden = false;
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
  modal?.querySelectorAll("[data-sinapsis-control-form]").forEach((panel) => {
    closeSinapsisControlForm(panel, { restoreFocus: false });
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
  modal?.querySelectorAll("[data-sinapsis-control-form]").forEach((panel) => {
    closeSinapsisControlForm(panel, { restoreFocus: false });
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
  modal?.querySelectorAll("[data-sinapsis-control-form]").forEach((panel) => {
    closeSinapsisControlForm(panel, { restoreFocus: false });
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

const syncSinapsisNoteRequirement = (form) => {
  const statusSelect = form?.querySelector("[data-sinapsis-status-select]");
  const note = form?.querySelector("[data-sinapsis-note]");
  const hint = form?.querySelector("[data-sinapsis-note-hint]");
  if (!statusSelect || !note || !hint) return;
  const isRequired = statusSelect.value === "Needs correction";
  note.toggleAttribute("required", isRequired);
  hint.hidden = !isRequired;
};

const closeSinapsisControlForm = (form, { restoreFocus = true } = {}) => {
  if (!form) return;
  form.hidden = true;
  const modal = form.closest(".modal");
  const trigger = modal?.querySelector(`[data-sinapsis-control-toggle][aria-controls="${CSS.escape(form.id)}"]`);
  trigger?.setAttribute("aria-expanded", "false");
  const errorBox = form.querySelector("[data-sinapsis-control-error]");
  if (errorBox) {
    errorBox.hidden = true;
    errorBox.textContent = "";
  }
  if (restoreFocus) trigger?.focus();
};

const openSinapsisControlForm = (form, trigger, { focus = true } = {}) => {
  if (!form) return;
  const modal = form.closest(".modal");
  document.querySelectorAll("[data-sinapsis-control-form]").forEach((panel) => {
    if (panel !== form) closeSinapsisControlForm(panel, { restoreFocus: false });
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
  modal?.querySelectorAll("[data-schedule-action-panel]").forEach((panel) => {
    closeScheduleActionPanel(panel, { restoreFocus: false });
  });
  syncSinapsisNoteRequirement(form);
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
  modal?.querySelectorAll("[data-sinapsis-control-form]").forEach((panel) => {
    closeSinapsisControlForm(panel, { restoreFocus: false });
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
    clearFocusedMode(modal);
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

  const sinapsisControlToggle = event.target.closest("[data-sinapsis-control-toggle]");
  if (sinapsisControlToggle) {
    event.preventDefault();
    const form = document.getElementById(sinapsisControlToggle.getAttribute("aria-controls"));
    if (!form) return;
    if (!form.hidden) {
      closeSinapsisControlForm(form);
    } else {
      openSinapsisControlForm(form, sinapsisControlToggle);
    }
    return;
  }

  const sinapsisControlCancel = event.target.closest("[data-sinapsis-control-cancel]");
  if (sinapsisControlCancel) {
    event.preventDefault();
    closeSinapsisControlForm(sinapsisControlCancel.closest("[data-sinapsis-control-form]"));
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
    const openSchedulePanel = document.querySelector(".modal.is-open [data-schedule-action-panel]:not([hidden])");
    if (openSchedulePanel) {
      event.preventDefault();
      closeScheduleActionPanel(openSchedulePanel);
      return;
    }
    const openStaffingControl = document.querySelector(".modal.is-open [data-staffing-control-form]:not([hidden])");
    if (openStaffingControl) {
      event.preventDefault();
      closeStaffingControlForm(openStaffingControl);
      return;
    }
    const openLogisticsControl = document.querySelector(".modal.is-open [data-logistics-control-form]:not([hidden])");
    if (openLogisticsControl) {
      event.preventDefault();
      closeLogisticsControlForm(openLogisticsControl);
      return;
    }
    const openFinanceControl = document.querySelector(".modal.is-open [data-finance-control-form]:not([hidden])");
    if (openFinanceControl) {
      event.preventDefault();
      closeFinanceControlForm(openFinanceControl);
      return;
    }
    const openSinapsisControl = document.querySelector(".modal.is-open [data-sinapsis-control-form]:not([hidden])");
    if (openSinapsisControl) {
      event.preventDefault();
      closeSinapsisControlForm(openSinapsisControl);
      return;
    }
    const openCommunicationsControl = document.querySelector(".modal.is-open [data-communications-control-form]:not([hidden])");
    if (openCommunicationsControl) {
      event.preventDefault();
      closeCommunicationsControlForm(openCommunicationsControl);
      return;
    }
    document.querySelectorAll(".modal.is-open").forEach(closeModal);
  }
});

document.querySelectorAll("[data-finance-control-form]").forEach((form) => {
  syncFinanceNoteRequirement(form);
  form.querySelector("[data-finance-status-select]")?.addEventListener("change", () => {
    syncFinanceNoteRequirement(form);
  });
});

document.querySelectorAll("[data-sinapsis-control-form]").forEach((form) => {
  syncSinapsisNoteRequirement(form);
  form.querySelector("[data-sinapsis-status-select]")?.addEventListener("change", () => {
    syncSinapsisNoteRequirement(form);
  });
});

document.querySelectorAll("[data-communications-control-form]").forEach((form) => {
  syncCommunicationsNoteRequirement(form);
  form.querySelector("[data-communications-status-select]")?.addEventListener("change", () => {
    syncCommunicationsNoteRequirement(form);
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

document.addEventListener("submit", (event) => {
  const passwordForm = event.target.closest("[data-confirm-password-submit]");
  if (passwordForm) {
    const message = passwordForm.dataset.confirmPasswordSubmit || "This action cannot be undone.";
    if (!window.confirm(message)) {
      event.preventDefault();
      return;
    }
    const password = window.prompt("Enter the confirmation password to continue:");
    if (password !== "7284") {
      event.preventDefault();
      window.alert("Incorrect password. The action was cancelled.");
      return;
    }
    const passwordInput = passwordForm.querySelector("input[name='deletion_password']");
    if (passwordInput) passwordInput.value = password;
  }

  const confirmForm = event.target.closest("[data-confirm-submit]");
  if (confirmForm) {
    const message = confirmForm.dataset.confirmSubmit || "Are you sure?";
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
  const partialShiftValues = ["Morning", "Afternoon", "Night"];
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
    const isOnsite = selectedFormat === "Onsite";

    onsiteFields.forEach((field) => {
      field.hidden = !isOnsite;
    });
    if (!isOnsite) {
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
  input.focus();
});

const syncKmDisableButton = (input) => {
  const button = input.closest("[data-km-field]")?.querySelector("[data-disable-km]");
  if (!button) return;
  button.hidden = input.value.trim() !== "";
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
  const row = staffAssignmentRow(field);
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
    form.classList.remove("is-saving");
    if (monthlyFormIsEmpty(form)) setMonthlyCellInactive(form);
  } catch (error) {
    form.classList.remove("is-saving");
    form.classList.add("is-error");
  }
};

const queueMonthlyRegistrationSave = (form) => {
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
  const panelHeight = panel.scrollHeight || 0;
  const openAbove = availableAbove >= panelHeight + 6 || availableAbove > availableBelow;
  panel.style.width = `${panelWidth}px`;
  panel.style.left = `${left}px`;
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
  return selected;
};

const selectedTeamMemberOption = (input) => {
  const row = input.closest(".staff-member-select-row");
  return Array.from(row?.querySelectorAll("[data-team-member-option]") || [])
    .find((option) => option.dataset.value === (input.value || "")) || null;
};

const staffAssignmentRow = (element) => element?.closest?.("[data-supervisor-row]") || null;

const resetParticipationWithoutTeamMember = (row) => {
  const teamMemberSelect = row?.querySelector("[data-team-member-select]");
  const participationSelect = row?.querySelector("[data-participation-select]");
  if (!teamMemberSelect || !participationSelect) return false;
  const hasTeamMember = Boolean(teamMemberSelect.value);
  Array.from(participationSelect.options).forEach((option) => {
    option.disabled = !hasTeamMember && option.value !== "Pending";
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
};

const initMemberMultiselects = (root = document) => {
  root.querySelectorAll("[data-member-multiselect]").forEach((picker) => {
    if (picker.dataset.initialized === "true") return;
    picker.dataset.initialized = "true";
    picker.addEventListener("toggle", () => {
      if (picker.open) {
        closeOtherMemberMultiselects(picker);
        positionMemberMultiselectPanel(picker);
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

document.addEventListener("click", (event) => {
  document.querySelectorAll("[data-member-multiselect][open]").forEach((picker) => {
    if (!picker.contains(event.target)) picker.open = false;
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll("[data-member-multiselect][open]").forEach((picker) => {
    picker.open = false;
  });
});

window.addEventListener("resize", () => {
  document.querySelectorAll("[data-member-multiselect][open]").forEach(positionMemberMultiselectPanel);
  document.querySelectorAll("[data-team-member-picker][open]").forEach(positionTeamMemberPickerPanel);
});

window.addEventListener("scroll", () => {
  document.querySelectorAll("[data-member-multiselect][open]").forEach(positionMemberMultiselectPanel);
  document.querySelectorAll("[data-team-member-picker][open]").forEach(positionTeamMemberPickerPanel);
}, true);

const syncTeamMemberSelect = (select) => {
  select.classList.remove("is-empty", "is-warning", "is-complete");
  const picker = select.closest(".staff-member-select-row")?.querySelector("[data-team-member-picker]");
  const summary = picker?.querySelector("[data-team-member-selected]");
  const option = selectedTeamMemberOption(select);
  picker?.classList.remove("is-empty", "is-warning", "is-complete");
  if (!option || !select.value) {
    select.classList.add("is-empty");
    picker?.classList.add("is-empty");
    if (summary) summary.innerHTML = '<span class="team-member-placeholder" title="Select a staff member to cover this role.">Role to cover</span>';
    const cardTitle = staffAssignmentRow(select)?.querySelector("[data-staff-card-title]");
    if (cardTitle) cardTitle.textContent = "Role to cover";
    syncStaffMemberAddressButton(select);
    syncStaffMemberEmailCell(select);
    syncFuelVehicleCells(staffAssignmentRow(select));
    syncFuel(staffAssignmentRow(select), { forceEmpty: true });
    syncVehicleDep(staffAssignmentRow(select), { forceEmpty: true });
    syncSeniority(staffAssignmentRow(select));
    resetParticipationWithoutTeamMember(staffAssignmentRow(select));
    return;
  }
  const state = option.dataset.state || "warning";
  select.classList.add(state === "completed" ? "is-complete" : "is-warning");
  picker?.classList.add(state === "completed" ? "is-complete" : "is-warning");
  if (summary) {
    const row = staffAssignmentRow(select);
    const location = option.querySelector(".staff-option-location")?.textContent.trim() || "";
    const seniorBadge = option.dataset.seniority === "true" ? '<span class="staff-option-senior">Senior</span>' : "";
    const carBadge = option.dataset.hasCar === "true" ? '<span class="staff-option-car">Has a car</span>' : "";
    const sessionCount = option.dataset.sessionCount || "0";
    const countBadge = `<span class="staff-option-count">(${sessionCount})</span>`;
    summary.innerHTML = `${state === "completed" ? '<span class="team-member-check">✓</span>' : ""}<span>${option.dataset.name || ""}</span>${location ? `<span class="staff-option-location">${location}</span>` : ""}${seniorBadge}${carBadge}${countBadge}`;
  }
  const cardTitle = staffAssignmentRow(select)?.querySelector("[data-staff-card-title]");
  if (cardTitle) cardTitle.textContent = option.dataset.name || "Role to cover";
  syncStaffMemberAddressButton(select);
  syncStaffMemberEmailCell(select);
  syncFuelVehicleCells(staffAssignmentRow(select));
  syncFuel(staffAssignmentRow(select), { forceEmpty: true });
  syncVehicleDep(staffAssignmentRow(select), { forceEmpty: true });
  syncSeniority(staffAssignmentRow(select));
  resetParticipationWithoutTeamMember(staffAssignmentRow(select));
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
  const button = document.createElement("button");
  button.className = "copy-icon-button email-invitation-copy-button";
  button.type = "button";
  button.dataset.copyInvitationEmail = "";
  button.setAttribute("aria-label", "Copy invitation email");
  button.title = "Copy invitation email";
  button.innerHTML = `
    <svg class="copy-icon" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="9" width="10" height="10" rx="2"></rect>
      <path d="M5 15V7a2 2 0 0 1 2-2h8"></path>
    </svg>
    <svg class="check-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="m5 12 4 4 10-10"></path>
    </svg>
    <span class="copy-button-feedback">Copied!</span>
  `;
  wrapper.appendChild(button);
  cell.replaceChildren(wrapper);
  initStaffGmailLinks(cell);
  initInvitationEmailCopyButtons(cell);
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
  return status !== "Pending";
};

const rowHasManualFeeOverride = (row) => row?.querySelector("[data-manual-fee-override]")?.value === "1";

const syncEditFeesButton = (row) => {
  if (!row) return;
  const button = row.querySelector("[data-edit-assignment-fees]");
  const status = row.querySelector("[data-participation-select]")?.value || "Pending";
  if (!button) return;
  button.hidden = status !== "Pending";
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

const CONTRACT_LINK = "https://drive.google.com/file/d/1FfzKcWq8pED3qv5yuzx2L9n_VEx0ZysM/view?usp=sharing";

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
      return { options: [], error: "Please complete all induction session options before copying this email." };
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

const buildSuccessfulApplicationEmail = (button) => {
  const fullName = cleanEmailValue(button.dataset.fullName);
  if (!fullName) return { error: "Potential entry full name is required." };
  const { options: inductionOptions, error: inductionOptionsError } = getInductionSessionOptions(button);
  if (inductionOptionsError) {
    return { error: inductionOptionsError };
  }
  if (!inductionOptions.length) {
    return { error: "Upcoming induction session date and time options are not configured." };
  }
  const { link: zoomLink, id: zoomId, password: zoomPassword } = POTENTIAL_INTERVIEW_ACCESS_DETAILS.Zoom;
  const safeName = escapeEmailHtml(fullName);
  const inductionOptionsHtml = inductionOptions.map((option, index) => `
      <div style="${index > 0 ? "margin-top:12px;padding-top:12px;border-top:1px solid #d9dfdc;" : ""}">
        ${inductionOptions.length > 1 ? `<p style="margin:0 0 4px;color:#62727a;font:700 11px Arial, Helvetica, sans-serif;text-transform:uppercase;">Option ${index + 1}</p>` : ""}
        <p style="margin:0;color:#00506b;font:700 18px/1.35 Arial, Helvetica, sans-serif;">${escapeEmailHtml(option.date)}</p>
        <p style="margin:3px 0 0;color:#00506b;font:700 18px/1.35 Arial, Helvetica, sans-serif;">${escapeEmailHtml(option.timeRange)}</p>
      </div>
    `).join("");
  const inductionOptionsText = inductionOptions
    .map((option, index) => inductionOptions.length > 1 ? `Option ${index + 1}: ${option.date}\n${option.timeRange}` : `${option.date}\n${option.timeRange}`)
    .join("\n\n");
  const bodyHtml = `
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Dear ${safeName},</p>
    <p style="margin:0 0 16px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">We are delighted to inform you that your application for the role of <strong>Examiner</strong> at Path International Examinations has been accepted. We are confident that you will be a valuable addition to our academic team.</p>
    <div style="margin:0 0 18px;padding:16px 18px;background:#e6f0f3;border-left:4px solid #00506b;border-radius:12px;">
      <p style="margin:0 0 10px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">To formally accept this offer and secure your place, please complete the following steps within 3 working days:</p>
      <ol style="margin:0;padding-left:20px;color:#111115;font:400 14px/1.55 Arial, Helvetica, sans-serif;">
        <li style="margin-bottom:8px;">Review, complete, sign and return <a href="${escapeEmailAttribute(CONTRACT_LINK)}" style="color:#00506b;font-weight:700;">this contract</a> to <a href="mailto:admin@pathexaminations.com" style="color:#00506b;font-weight:700;">admin@pathexaminations.com</a>, together with a professional profile picture.</li>
        <li>Confirm your availability for <strong>ONE</strong> of the upcoming online induction sessions.</li>
      </ol>
    </div>
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      <p style="margin:0 0 10px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">Confirm your availability for <strong>ONE</strong> of the upcoming online induction sessions:</p>
      ${inductionOptionsHtml}
    </div>
    <div style="margin:0 0 18px;padding:16px 18px;background:#f1f3f2;border:1px solid #d9dfdc;border-radius:12px;">
      <p style="margin:0 0 10px;color:#00506b;font:700 15px Arial, Helvetica, sans-serif;">The Zoom access details are as follows:</p>
      <p style="margin:0 0 6px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Link: <a href="${escapeEmailAttribute(zoomLink)}" style="color:#00506b;font-weight:700;">${escapeEmailHtml(zoomLink)}</a></p>
      <p style="margin:0 0 6px;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Zoom ID: <strong>${escapeEmailHtml(zoomId)}</strong></p>
      <p style="margin:0;color:#111115;font:400 14px/1.5 Arial, Helvetica, sans-serif;">Password: <strong>${escapeEmailHtml(zoomPassword)}</strong></p>
    </div>
    <p style="margin:0 0 14px;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Should you have any questions or require any further information, please let us know.</p>
    <p style="margin:0;color:#111115;font:400 15px/1.55 Arial, Helvetica, sans-serif;">Welcome to Path International Examinations. We look forward to working with you.</p>
  `;
  const html = pathEmailShell({
    label: "Successful application",
    title: "Your application has been accepted",
    bodyHtml,
  });
  const text = `Dear ${fullName},\n\nWe are delighted to inform you that your application for the role of Examiner at Path International Examinations has been accepted. We are confident that you will be a valuable addition to our academic team.\n\nTo formally accept this offer and secure your place, please complete the following steps within 3 working days:\n\n* Review, complete, sign and return this contract to admin@pathexaminations.com, together with a professional profile picture:\n${CONTRACT_LINK}\n\n* Confirm your availability for ONE of the upcoming online induction sessions:\n\n${inductionOptionsText}\n\nThe Zoom access details are as follows:\n\nLink: ${zoomLink}\nZoom ID: ${zoomId}\nPassword: ${zoomPassword}\n\nShould you have any questions or require any further information, please let us know.\n\nWelcome to Path International Examinations. We look forward to working with you.\n\nBest regards,\n\nPath International Examinations`;
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
  if (sessionFormat === "Online") return "💻";
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
    row?.querySelectorAll("[data-team-member-option]").forEach((option) => {
      option.addEventListener("click", () => {
        if (option.disabled) return;
        select.value = option.dataset.value || "";
            row.querySelector("[data-team-member-picker]").open = false;
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
        positionTeamMemberPickerPanel(event.currentTarget);
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
  initPotentialGmailButtons(root);
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
initPotentialGmailButtons();

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
      try {
        await copyTextToClipboard(button.dataset.copyText || "");
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
};

initCopyTextButtons();

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
  feedback.innerHTML = `<div class="flash error">${message}</div>`;
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
    "Simple logistics": "staff-logistics-simple-logistics",
    "Complex logistics": "staff-logistics-complex-logistics",
  }[value] || "staff-logistics-does-not-apply";
  tag.classList.add(logisticsClass);
  tag.textContent = value || "Does not apply";
};

const syncParticipationSelect = (select) => {
  const row = staffAssignmentRow(select);
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
    const isLive = select.value === "Pending";
    const isLocked = select.value !== "Pending";
    chip.textContent = isLocked ? "Locked" : "Live calculation";
    chip.classList.toggle("is-live", isLive);
    chip.classList.toggle("is-locked", isLocked);
    chip.hidden = !isLive && !isLocked;
  }
  syncCalculatedFieldLocks(row);
  syncInvitationEmailCopyButtons(select.closest("[data-session-members-form]"));
  if (select.value === "Pending") {
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

const logisticsControlIsActive = (control) => ["Simple logistics", "Complex logistics"].includes(control?.value);

const activeLogisticsControls = (form) => logisticsControls(form).filter(logisticsControlIsActive);

const rowHasActiveLogisticsControl = (row) => Array.from(row?.querySelectorAll("[data-logistics-control]") || []).some(logisticsControlIsActive);

const syncStaffLogisticsControl = (control) => {
  if (!control) return;
  control.classList.remove(
    ...STAFF_LOGISTICS_CLASSES,
  );
  const logisticsClass = {
    "Does not apply": "staff-logistics-does-not-apply",
    "Simple logistics": "staff-logistics-simple-logistics",
    "Complex logistics": "staff-logistics-complex-logistics",
  }[control.value] || "staff-logistics-does-not-apply";
  control.classList.add(logisticsClass);
  const row = control.closest("[data-supervisor-row]");
  syncStaffHeaderLogisticsTag(row, control.value);
  const hiddenInput = row?.querySelector("[data-logistics-enabled-input]");
  if (hiddenInput) hiddenInput.value = logisticsControlIsActive(control) ? "1" : "";
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

const syncLogisticsSection = (form) => {
  if (!form) return;
  const section = form.querySelector("[data-logistics-section]");
  if (!section) return;
  section.hidden = activeLogisticsControls(form).length === 0 && !formHasLogisticsConcepts(form);
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
  const row = select.closest("[data-logistics-concept-row]");
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
      button.disabled = !button.dataset.openModal;
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
  syncInvitationEmailCopyButtons(select.closest("[data-session-members-form]"));
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
  if (select.value) {
    button.dataset.openModal = `provider-details-${select.value}`;
    button.disabled = false;
  } else {
    delete button.dataset.openModal;
    button.disabled = true;
  }
};

const syncLogisticsProviderForType = (typeSelect) => {
  const row = typeSelect.closest("[data-logistics-concept-row]");
  const providerSelect = row?.querySelector("[data-logistics-provider-select]");
  if (!providerSelect) return;
  const selectedTypeId = typeSelect.value;
  let selectedProviderIsAvailable = false;
  Array.from(providerSelect.options).forEach((option) => {
    if (!option.value) {
      option.hidden = false;
      option.disabled = false;
      return;
    }
    const matchesSelectedType = Boolean(selectedTypeId) && option.dataset.providerTypeId === selectedTypeId;
    option.hidden = !matchesSelectedType;
    option.disabled = !matchesSelectedType;
    if (matchesSelectedType && option.selected) selectedProviderIsAvailable = true;
  });
  providerSelect.disabled = !selectedTypeId;
  if (!selectedTypeId || !selectedProviderIsAvailable) {
    providerSelect.value = "";
  }
  syncLogisticsProviderDetailsButton(providerSelect);
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
  root.querySelectorAll("[data-logistics-status]").forEach((select) => {
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
    select.addEventListener("change", () => syncLogisticsProviderDetailsButton(select));
    syncLogisticsProviderDetailsButton(select);
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

  root.querySelectorAll("[data-session-members-form]").forEach(syncLogisticsSection);
};

const initSessionMemberRows = (root = document) => {
  initMemberMultiselects(root);
  initTeamMemberSelects(root);
  initStaffGmailLinks(root);
  initParticipationSelects(root);
  initStaffCollapsibleSections(root);
  initLogisticsControls(root);
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
    if (rowHasManualFeeOverride(row)) {
      enableManualFeeOverride(row);
      saveManualFeeOverride(row);
    }
    syncEditFeesButton(row);
    syncAssignmentTotalFee(row);
  });
  syncInvitationEmailCopyButtons(root);
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
    target.appendChild(row);
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
    const isArranged = status.value === "Interview arranged" || status.value === "Interview scheduled";
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
  item.textContent = message;
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
  const address = form.querySelector("[name='full_address']")?.value.trim() || "";
  const availability = form.querySelector("[name='available_in_logistics']:checked")?.value || "";
  submit.disabled = !(providerType && name && address && availability);
  syncProviderTypePreview(form);
};

const providerFormData = (form) => {
  const data = new FormData(form);
  ["name", "full_address", "type_name"].forEach((name) => {
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

const renderProviderRow = (provider) => {
  const row = document.createElement("tr");
  row.dataset.providerRow = "";
  row.dataset.providerId = String(provider.id);
  row.innerHTML = `
    <td data-provider-type-cell>${providerTypeCellHtml(provider)}</td>
    <td class="strong" data-provider-name-cell></td>
    <td class="provider-address-cell" data-provider-address-cell></td>
    <td><button class="mini-button" type="button" data-provider-history-button>Notes</button></td>
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
            <input name="full_address" value="" maxlength="500" required>
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
      time.textContent = `${payload.note.created_on} h${payload.note.created_by ? ` | ${payload.note.created_by}` : ""}`;
      const text = document.createElement("p");
      text.textContent = payload.note.comment;
      entry.append(time, text);
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
      element.matches(".copy-icon-button, [data-copy-text], [data-copy-invitation-email], [data-staff-address-copy], [data-copy-journey-link], [data-bulk-email-link], [data-acceptance-draft-save], [data-delete-logistics-concept], [data-remove-supervisor-row], [data-add-time-range], [data-remove-time-range], [data-disable-km], [data-edit-assignment-fees], [data-clear-selection], [data-provider-type-create-form] button") ||
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
