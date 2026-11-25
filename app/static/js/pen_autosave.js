/* One queue per card. Snapshots keep edits made during an upload intact. */
(() => {
  class PenCardAutosave {
    constructor(adapter, revision = 0) {
      this.adapter = adapter; this.revision = revision;
      this.sequence = 0; this.savedSequence = 0;
      this.timer = null; this.inFlight = null; this.paused = false; this.conflict = false; this.removed = false; this.attempted = false;
    }
    get dirty() { return !this.removed && (this.sequence !== this.savedSequence || Boolean(this.inFlight)); }
    notify(state, message) { this.adapter.status(state, message); }
    change(delay = 650) {
      if (this.removed || this.paused) return;
      this.sequence++;
      if (this.conflict) return;
      clearTimeout(this.timer);
      const invalid = this.adapter.validate();
      this.notify(invalid ? 'invalid' : 'pending', invalid || 'Waiting to save…');
      if (!invalid) this.timer = setTimeout(() => this.flush(), delay);
    }
    async flush() {
      clearTimeout(this.timer);
      if (this.removed || this.paused || this.conflict) return false;
      if (this.inFlight) return this.inFlight;
      if (this.sequence === this.savedSequence) return true;
      const invalid = this.adapter.validate();
      if (invalid) { this.notify('invalid', invalid); return false; }
      const sequence = this.sequence, snapshot = this.adapter.snapshot();
      this.attempted = true;
      this.notify('saving', 'Saving…');
      let success = false;
      this.inFlight = Promise.resolve().then(() => this.adapter.save(snapshot, this.revision)).then(result => {
        this.revision = result.candidate.revision;
        this.adapter.saved(result.candidate, snapshot);
        this.savedSequence = sequence; success = true;
        this.notify(this.sequence === sequence ? 'saved' : 'pending', this.sequence === sequence ? 'Saved automatically' : 'Waiting to save latest changes…');
        return true;
      }).catch(error => {
        this.conflict = error.status === 409;
        this.notify(this.conflict ? 'conflict' : 'error', error.message || 'Could not save. Please retry.');
        return false;
      }).finally(() => {
        this.inFlight = null;
        this.adapter.settled?.();
        if (success && this.sequence !== sequence && !this.paused && !this.removed) this.timer = setTimeout(() => this.flush(), 50);
      });
      return this.inFlight;
    }
    async pause() { this.paused = true; clearTimeout(this.timer); if (this.inFlight) await this.inFlight; }
    resume() { this.paused = false; }
    remove() { this.removed = true; clearTimeout(this.timer); }
  }
  window.PenCardAutosave = PenCardAutosave;
})();
