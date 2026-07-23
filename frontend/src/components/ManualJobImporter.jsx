import { useState } from "react";
import { JobService } from "../services/jobs";
import { useI18n } from "../i18n/useI18n";

const EMPTY_LISTING = {
  title: "",
  company: "",
  location: "",
  external_url: "",
  description: "",
};

export function ManualJobImporter({ onImported }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [listing, setListing] = useState(EMPTY_LISTING);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const update = (field) => (event) => {
    setListing((current) => ({ ...current, [field]: event.target.value }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await JobService.importManual({
        title: listing.title.trim(),
        company: listing.company.trim(),
        location: listing.location.trim() || null,
        external_url: listing.external_url.trim(),
        description: listing.description.trim() || null,
      });
      setListing(EMPTY_LISTING);
      setOpen(false);
      await onImported?.();
    } catch (importError) {
      setError(importError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass-panel p-3 p-md-4 mb-4" aria-labelledby="manual-import-title">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3">
        <div>
          <h2 id="manual-import-title" className="h5 mb-1">{t("jobs.import.title")}</h2>
          <p className="text-secondary mb-0">{t("jobs.import.copy")}</p>
        </div>
        <button type="button" className="btn btn-outline-light" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          <i className={`bi ${open ? "bi-x-lg" : "bi-plus-lg"} me-2`} aria-hidden="true" />
          {open ? t("jobs.import.close") : t("jobs.import.open")}
        </button>
      </div>
      {open && (
        <form className="mt-4" onSubmit={submit}>
          {error && <div className="alert alert-danger" role="alert">{error}</div>}
          <div className="row g-3">
            <label className="col-12 col-md-6 form-label">
              <span>{t("jobs.import.role")}</span>
              <input className="form-control mt-1" value={listing.title} onChange={update("title")} maxLength="240" required />
            </label>
            <label className="col-12 col-md-6 form-label">
              <span>{t("jobs.import.company")}</span>
              <input className="form-control mt-1" value={listing.company} onChange={update("company")} maxLength="240" required />
            </label>
            <label className="col-12 col-md-6 form-label">
              <span>{t("jobs.import.url")}</span>
              <input className="form-control mt-1" type="url" value={listing.external_url} onChange={update("external_url")} maxLength="2048" placeholder="https://…" required />
            </label>
            <label className="col-12 col-md-6 form-label">
              <span>{t("jobs.import.location")}</span>
              <input className="form-control mt-1" value={listing.location} onChange={update("location")} maxLength="500" />
            </label>
            <label className="col-12 form-label">
              <span>{t("jobs.import.description")}</span>
              <textarea className="form-control mt-1" rows="5" value={listing.description} onChange={update("description")} maxLength="100000" />
            </label>
          </div>
          <div className="d-flex align-items-center gap-3 mt-3">
            <button className="btn btn-primary" disabled={busy}>{busy ? t("jobs.import.saving") : t("jobs.import.save")}</button>
            <small className="text-secondary"><i className="bi bi-device-ssd me-1" aria-hidden="true" />{t("jobs.import.local")}</small>
          </div>
        </form>
      )}
    </section>
  );
}
