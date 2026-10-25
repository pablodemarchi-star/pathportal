// Use the official-confirmation content helpers; present their data as a web interface.
(() => {
  const make = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  };
  const link = (label, href) => {
    try {
      const url = new URL(href);
      if (!["https:", "http:", "mailto:"].includes(url.protocol)) return null;
      const element = make("a", "staff-detail-link", label);
      element.href = url.href;
      if (url.protocol !== "mailto:") {
        element.target = "_blank";
        element.rel = "noopener noreferrer";
      }
      return element;
    } catch { return null; }
  };
  const appendLink = (parent, label, href) => {
    const element = link(label, href);
    if (element) parent.append(element);
  };
  const hydrate = (dialog) => {
    if (dialog.dataset.initialized) return;
    dialog.querySelectorAll("[data-staff-session-payload]").forEach((root) => {
      const data = JSON.parse(root.dataset.staffSessionPayload);
      const role = data.role;
      const remote = role === "Emergency contact" || (role === "Supervisor" && data.is_remote);
      const arrival = root.querySelector("[data-staff-arrival]");
      if (remote) {
        arrival.textContent = "Remote assignment · no venue attendance required";
      } else {
        arrival.textContent = "Arrive ";
        const minimum = make("em");
        minimum.append(make("u", "", "at least"));
        arrival.append(minimum, ` ${officialArrivalMinutesForRole(role)} minutes before the start.`);
      }
      const materials = root.querySelector("[data-staff-materials]");
      const rows = role === "Emergency contact"
        ? [["Emergency contact manual", "Read and fully understand the manual before the session. Raise any questions with Path Examinations in advance.", EMERGENCY_CONTACT_MANUAL_URL]]
        : officialMaterialRows(role, data).filter(([title]) =>
          (!title.includes("Back-up material for examiners")
            || (role === "Supervisor" && data.participation_confirmed))
          && !(role === "Examiner" && title.includes("Material for examiners"))
          && !(role === "Supervisor" && data.is_remote
            && (title.includes("Supervisor guidelines") || title.includes("Exam box shipment"))));
      rows.forEach(([title, description, url]) => {
        const item = make("div", "staff-detail-material");
        item.append(make("h4", "", title), make("p", "", description));
        if (url) appendLink(item, "Open resource ↗", url);
        else if (!title.includes("shipment")) item.append(make("small", "staff-detail-muted", "Link to be confirmed"));
        materials.append(item);
      });
      if (!rows.length) root.querySelector("[data-staff-materials-section]").hidden = true;
      const duties = role === "Emergency contact" ? {
        title: "Your responsibilities",
        items: ["Remain available and monitor your phone throughout the session, particularly at the beginning and end.",
          "You may receive a call from the Supervisor, or the Exam centre may contact Path via the official Path WhatsApp number.",
          "Be reachable from 50 minutes before the scheduled start, when the Supervisor arrives at the venue.",
          "Respond to, assess and help resolve operational situations using sound judgement and providing appropriate justification for your decisions or guidance."]
      } : ["Supervisor", "Examiner"].includes(role) ? null : officialFinalInstructions(role);
      if (duties) {
        root.querySelector("[data-staff-responsibilities-title]").textContent = duties.title.toLowerCase().replace(/^./, (c) => c.toUpperCase());
        duties.items.forEach((text) => root.querySelector("[data-staff-responsibilities]").append(make("li", "", text)));
      } else root.querySelector("[data-staff-responsibilities-section]").hidden = true;
      if (remote) root.querySelector("[data-staff-travel-section]").hidden = true;
      else {
        const travel = officialTravelCopy(role, data.logistics_status || "Does not apply", data.logistics_url || "");
        travel.text.split(/\n+/).filter((text) => text && text !== data.logistics_url).forEach((text) => {
          root.querySelector("[data-staff-travel]").append(make("p", "", text));
        });
        if (data.logistics_url && data.logistics_status !== "Does not apply") appendLink(root.querySelector("[data-staff-logistics-link]"), "Open logistics folder ↗", data.logistics_url);
      }
      if (data.participation_confirmed) return;
      const subject = `Re: Path exam session invitation - ${data.session_name || "Exam session"} - ${data.full_name}`;
      const confirmation = make("div", "staff-detail-confirm-form");
      confirmation.dataset.staffParticipationControl = "";
      const confirmButton = make("button", "staff-detail-link is-confirm", "Confirm participation");
      confirmButton.type = "button";
      confirmButton.dataset.staffParticipationOpen = "";
      const confirmPanel = make("dialog", "staff-detail-decline-confirmation staff-detail-confirm-participation");
      confirmPanel.dataset.staffParticipationPanel = "";
      confirmPanel.ariaLabel = "Confirm participation";
      confirmPanel.append(make("h3", "", "Confirm your participation?"));
      confirmPanel.append(make("p", "", "Please confirm that you accept this exam session assignment and can access the session materials."));
      confirmPanel.addEventListener("close", () => confirmButton.focus());
      const confirmForm = make("form");
      confirmForm.method = "post";
      confirmForm.action = data.confirmation_url;
      const csrf = make("input");
      csrf.type = "hidden";
      csrf.name = "csrf_token";
      csrf.value = data.confirmation_csrf;
      const reconfirmParticipation = make("button", "staff-detail-link is-confirm", "Yes, confirm participation");
      reconfirmParticipation.type = "submit";
      const cancelParticipation = make("button", "staff-detail-link is-question", "Cancel");
      cancelParticipation.type = "button";
      cancelParticipation.dataset.staffParticipationCancel = "";
      confirmForm.append(csrf, reconfirmParticipation, cancelParticipation);
      confirmPanel.append(confirmForm);
      confirmation.append(confirmButton, confirmPanel);
      root.querySelector("[data-staff-response-actions]").append(confirmation);
      const actions = [
        ["Ask a question", "Dear Path Team,\r\n\r\nBefore confirming my participation, I would like to ask the following question(s):", "is-question"],
      ];
      actions.forEach(([label, body, tone]) => {
        let href = buildMailtoLink({to: "admin@pathexaminations.com", subject, body});
        if (tone === "is-question" && ["Examiner", "Supervisor"].includes(role)) {
          const questionRole = role + (data.is_remote ? " (remote)" : "");
          const message = [
            `*${data.session_name} (${data.session_date_short || data.session_date})*`,
            `- *${questionRole}: ${data.full_name}*`,
            "",
            "¡Hola, equipo de Path!",
            "",
            "Tengo la siguiente consulta sobre esta sesión de examen:",
          ].join("\n");
          href = `https://wa.me/5491150954847?text=${encodeURIComponent(message)}`;
        }
        const action = link(label, href);
        action.classList.add(tone);
        root.querySelector("[data-staff-response-actions]").append(action);
      });
      const decline = make("div", "staff-detail-decline-control");
      decline.dataset.staffDeclineControl = "";
      const declineButton = make("button", "staff-detail-link is-decline", "Decline session");
      declineButton.type = "button";
      declineButton.dataset.staffDeclineOpen = "";
      const panel = make("dialog", "staff-detail-decline-confirmation");
      panel.dataset.staffDeclinePanel = "";
      panel.ariaLabel = "Decline session confirmation";
      panel.append(make("h3", "", "Decline this session?"));
      panel.append(make("p", "", "Are you sure you want to decline this session? Your place will be released."));
      panel.addEventListener("close", () => declineButton.focus());
      const declineForm = make("form");
      declineForm.method = "post";
      declineForm.action = data.decline_url;
      [["csrf_token", data.confirmation_csrf], ["reconfirmed", "1"]].forEach(([name, value]) => {
        const input = make("input");
        input.type = "hidden";
        input.name = name;
        input.value = value;
        declineForm.append(input);
      });
      const reconfirm = make("button", "staff-detail-link is-decline", "Yes, decline session");
      reconfirm.type = "submit";
      const cancel = make("button", "staff-detail-link is-question", "Cancel");
      cancel.type = "button";
      cancel.dataset.staffDeclineCancel = "";
      declineForm.append(reconfirm, cancel);
      panel.append(declineForm);
      decline.append(declineButton, panel);
      root.querySelector("[data-staff-response-actions]").append(decline);
    });
    dialog.querySelectorAll("[data-staff-phone]").forEach((item) => {
      const href = officialContactWhatsAppUrl(item.dataset.staffPhone);
      if (href) { const action = link(item.textContent.trim(), href); if (action) item.replaceChildren(action); }
    });
    dialog.dataset.initialized = "true";
  };
  let opener;
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-staff-session-open]");
    if (trigger) {
      const dialog = document.getElementById(trigger.dataset.staffSessionOpen);
      if (!dialog) return;
      hydrate(dialog);
      opener = trigger;
      dialog.showModal();
      document.body.classList.add("staff-session-detail-open");
      dialog.scrollTop = 0;
    }
    const participationOpen = event.target.closest("[data-staff-participation-open]");
    if (participationOpen) {
      const panel = participationOpen.closest("[data-staff-participation-control]").querySelector("[data-staff-participation-panel]");
      panel.showModal();
      panel.querySelector('button[type="submit"]').focus();
    }
    const participationCancel = event.target.closest("[data-staff-participation-cancel]");
    if (participationCancel) {
      participationCancel.closest("[data-staff-participation-control]").querySelector("[data-staff-participation-panel]").close();
    }
    const declineOpen = event.target.closest("[data-staff-decline-open]");
    if (declineOpen) {
      const panel = declineOpen.closest("[data-staff-decline-control]").querySelector("[data-staff-decline-panel]");
      panel.showModal();
      panel.querySelector('button[type="submit"]').focus();
    }
    const declineCancel = event.target.closest("[data-staff-decline-cancel]");
    if (declineCancel) {
      const control = declineCancel.closest("[data-staff-decline-control]");
      control.querySelector("[data-staff-decline-panel]").close();
    }
    const close = event.target.closest("[data-staff-session-close]");
    if (close) close.closest("dialog").close();
  });
  document.querySelectorAll("dialog.staff-session-detail").forEach((dialog) => {
    dialog.addEventListener("close", () => { document.body.classList.remove("staff-session-detail-open"); opener?.focus(); });
    dialog.addEventListener("click", (event) => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
    });
  });
})();

(() => {
  const sections = Array.from(document.querySelectorAll("[data-staff-end-checks]"));
  if (!sections.length) return;
  const updateCount = (section) => {
    const checked = section.querySelectorAll("[data-end-check]:checked").length;
    const total = section.querySelectorAll("[data-end-check]").length;
    section.querySelector("[data-end-checks-title]").textContent = `End-of-session checks (${checked}/${total})`;
  };
  const updateAvailability = (section) => {
    updateCount(section);
    const opensAt = Date.parse(section.dataset.opensAt);
    const available = Number.isFinite(opensAt) && Date.now() >= opensAt;
    const status = section.querySelector("[data-end-checks-status]");
    status.textContent = available ? "Available" : "Available on exam day";
    status.classList.toggle("is-available", available);
    section.querySelectorAll("[data-end-check]").forEach((input) => {
      if (!input.dataset.saving) input.disabled = !available;
      input.closest(".staff-end-check-row").classList.toggle("is-disabled", !available);
    });
    section.querySelectorAll("[data-end-checks-folder]").forEach((folder) => {
      const folderAvailable = available && Boolean(folder.dataset.folderUrl);
      folder.href = folderAvailable ? folder.dataset.folderUrl : "#";
      folder.classList.toggle("is-disabled", !folderAvailable);
      folder.setAttribute("aria-disabled", String(!folderAvailable));
      if (folderAvailable) folder.removeAttribute("tabindex");
      else folder.setAttribute("tabindex", "-1");
    });
  };
  sections.forEach((section) => {
    updateAvailability(section);
    section.querySelectorAll("[data-end-checks-folder]").forEach((folder) => {
      folder.addEventListener("click", (event) => {
        if (event.currentTarget.getAttribute("aria-disabled") === "true") event.preventDefault();
      });
    });
    section.querySelectorAll("[data-end-check]").forEach((input) => {
      input.addEventListener("change", async () => {
        const checked = input.checked;
        updateCount(section);
        const feedback = section.querySelector("[data-end-checks-feedback]");
        input.dataset.saving = "true";
        input.disabled = true;
        feedback.textContent = "Saving…";
        try {
          const response = await fetch(section.dataset.saveUrl, {
            method: "POST", headers: { Accept: "application/json" },
            body: new URLSearchParams({ csrf_token: section.dataset.csrf, check: input.dataset.endCheck, checked: checked ? "1" : "0" }),
          });
          const result = await response.json();
          if (!response.ok || !result.ok) throw new Error(result.error || "Your changes could not be saved. Please try again.");
          input.checked = result.checked;
          feedback.textContent = "Saved";
        } catch (error) {
          input.checked = !checked;
          feedback.textContent = error.message || "Your changes could not be saved. Please try again.";
        } finally {
          delete input.dataset.saving;
          updateAvailability(section);
        }
      });
    });
  });
  const refresh = () => sections.forEach(updateAvailability);
  const scheduleUnlock = () => {
    const now = Date.now();
    const upcoming = sections.map((section) => Date.parse(section.dataset.opensAt)).filter((at) => at > now);
    if (!upcoming.length) return;
    window.setTimeout(() => { refresh(); scheduleUnlock(); }, Math.min(Math.min(...upcoming) - now, 2147483647));
  };
  scheduleUnlock();
  window.setInterval(refresh, 30000);
  window.addEventListener("focus", refresh);
})();
