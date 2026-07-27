import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { registerProfile } from "../lib/admin";

const CLASS_OPTIONS = Array.from({ length: 12 }, (_, index) => `K${index + 1}`);
const DEFAULT_SECTION_OPTIONS = ["A", "B", "C", "D"];
const FACE_VIEW_FIELDS = [
  { key: "straight", label: "Look straight" },
  { key: "left", label: "Turn slightly left" },
  { key: "right", label: "Turn slightly right" },
  { key: "top", label: "Tilt face up" },
  { key: "down", label: "Tilt face down" }
];

const initialForm = {
  profileType: "faculty",
  name: "",
  email: "",
  department: "",
  className: "",
  sectionName: "",
  rollNumber: "",
  checkInTime: "09:00",
  checkOutTime: "17:00"
};

function buildInitialForm(search) {
  const params = new URLSearchParams(search);
  const requestedType = params.get("type");
  const profileType = requestedType === "student" ? "student" : "faculty";

  return {
    ...initialForm,
    profileType,
    className: params.get("class_name") || "",
    sectionName: params.get("section_name") || ""
  };
}

function getCameraSupportMessage() {
  if (!window.isSecureContext) {
    return "Camera access requires HTTPS or localhost. Chrome blocks webcam permission on this non-secure network address.";
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    return "Camera capture is not available in this browser.";
  }

  return "";
}

export function RegistrationPage() {
  const location = useLocation();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const captureCanvasRef = useRef(null);
  const [form, setForm] = useState(() => buildInitialForm(location.search));
  const [sectionOptions, setSectionOptions] = useState(() => {
    const initial = buildInitialForm(location.search).sectionName;
    return initial && !DEFAULT_SECTION_OPTIONS.includes(initial)
      ? [...DEFAULT_SECTION_OPTIONS, initial]
      : DEFAULT_SECTION_OPTIONS;
  });
  const [isAddingSection, setIsAddingSection] = useState(false);
  const [newSectionName, setNewSectionName] = useState("");
  const [imageFiles, setImageFiles] = useState({});
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [cameraReady, setCameraReady] = useState(false);
  const [selectedCaptureView, setSelectedCaptureView] = useState(FACE_VIEW_FIELDS[0].key);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const nextForm = buildInitialForm(location.search);
    setForm(nextForm);
    setSectionOptions(
      nextForm.sectionName && !DEFAULT_SECTION_OPTIONS.includes(nextForm.sectionName)
        ? [...DEFAULT_SECTION_OPTIONS, nextForm.sectionName]
        : DEFAULT_SECTION_OPTIONS
    );
    setIsAddingSection(false);
    setNewSectionName("");
    setImageFiles({});
    setCameraOpen(false);
    setCameraLoading(false);
    setCameraError("");
    setCameraReady(false);
    setSelectedCaptureView(FACE_VIEW_FIELDS[0].key);
    setMessage("");
  }, [location.search]);

  const [previewUrls, setPreviewUrls] = useState({});

  useEffect(() => {
    const nextPreviewUrls = FACE_VIEW_FIELDS.reduce((accumulator, view) => {
      const file = imageFiles[view.key];
      accumulator[view.key] = file ? URL.createObjectURL(file) : "";
      return accumulator;
    }, {});

    setPreviewUrls(nextPreviewUrls);

    return () => {
      Object.values(nextPreviewUrls).forEach((url) => {
        if (url) {
          URL.revokeObjectURL(url);
        }
      });
    };
  }, [imageFiles]);

  useEffect(() => () => {
    stopCameraStream();
  }, []);

  useEffect(() => {
    async function attachStream() {
      if (!cameraOpen || !videoRef.current || !streamRef.current) {
        return;
      }

      try {
        videoRef.current.srcObject = streamRef.current;
        await videoRef.current.play();
        setCameraReady(true);
      } catch (error) {
        setCameraReady(false);
        setCameraError(error?.message || "Unable to render the camera preview.");
      }
    }

    attachStream();
  }, [cameraOpen, selectedCaptureView]);

  function updateField(event) {
    const { name, value } = event.target;

    setForm((current) => {
      if (name === "profileType") {
        return {
          ...current,
          profileType: value,
          department: value === "faculty" ? current.department : "",
          className: value === "student" ? current.className : "",
          sectionName: value === "student" ? current.sectionName : "",
          rollNumber: value === "student" ? current.rollNumber : ""
        };
      }

      return {
        ...current,
        [name]: value
      };
    });
  }

  function updateFile(viewKey, event) {
    const file = event.target.files?.[0] || null;
    setImageFiles((current) => ({
      ...current,
      [viewKey]: file
    }));
  }

  function stopCameraStream() {
    setCameraReady(false);

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }

  async function openCamera(viewKey = FACE_VIEW_FIELDS[0].key) {
    const supportMessage = getCameraSupportMessage();

    if (supportMessage) {
      setCameraError(supportMessage);
      return;
    }

    setCameraLoading(true);
    setCameraError("");
    setSelectedCaptureView(viewKey);

    try {
      stopCameraStream();
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user"
        },
        audio: false
      });

      streamRef.current = stream;
      setCameraOpen(true);
    } catch (error) {
      if (error?.name === "NotAllowedError") {
        setCameraError("Camera permission was denied. Allow camera access in Chrome and try again.");
      } else if (error?.name === "NotFoundError") {
        setCameraError("No camera was found on this device.");
      } else {
        setCameraError(error?.message || "Unable to access the camera.");
      }
      setCameraOpen(false);
    } finally {
      setCameraLoading(false);
    }
  }

  function closeCamera() {
    stopCameraStream();
    setCameraOpen(false);
    setCameraError("");
  }

  async function capturePhoto() {
    const video = videoRef.current;
    const canvas = captureCanvasRef.current;

    if (!video || !canvas || !selectedCaptureView) {
      setCameraError("Camera preview is not ready yet.");
      return;
    }

    if (!cameraReady || !video.videoWidth || !video.videoHeight) {
      setCameraError("Wait for the camera preview to load before capturing.");
      return;
    }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");

    if (!context) {
      setCameraError("Unable to prepare captured image.");
      return;
    }

    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", 0.92);
    });

    if (!blob) {
      setCameraError("Unable to capture photo. Please try again.");
      return;
    }

    const capturedFile = new File(
      [blob],
      `${form.name.trim().replace(/\s+/g, "-").toLowerCase() || "profile"}-${selectedCaptureView}.jpg`,
      { type: "image/jpeg" }
    );

    setImageFiles((current) => ({
      ...current,
      [selectedCaptureView]: capturedFile
    }));
    setMessage(`${FACE_VIEW_FIELDS.find((view) => view.key === selectedCaptureView)?.label || "Selected"} image captured.`);
    setCameraError("");
  }

  function commitNewSection() {
    const normalized = newSectionName.trim();

    if (!normalized) {
      setMessage("Enter a section name before adding it.");
      return;
    }

    setSectionOptions((current) => (current.includes(normalized) ? current : [...current, normalized]));
    setForm((current) => ({
      ...current,
      sectionName: normalized
    }));
    setNewSectionName("");
    setIsAddingSection(false);
    setMessage("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage("");

    if (!form.name.trim()) {
      setMessage("Full name is required.");
      return;
    }

    if (form.profileType === "student") {
      if (!form.className.trim()) {
        setMessage("Class is required for student registration.");
        return;
      }

      if (!form.sectionName.trim()) {
        setMessage("Section is required for student registration.");
        return;
      }

      if (!form.rollNumber.trim()) {
        setMessage("Roll number is required for student registration.");
        return;
      }
    }

    const missingViews = FACE_VIEW_FIELDS.filter((view) => !imageFiles[view.key]);
    if (missingViews.length) {
      setMessage(`Please provide all required face views: ${missingViews.map((view) => view.label).join(", ")}.`);
      return;
    }

    setSubmitting(true);

    try {
      const formData = new FormData();
      formData.append("profile_type", form.profileType);
      formData.append("name", form.name.trim());
      formData.append("image", imageFiles.straight);
      formData.append("email", form.email.trim());
      formData.append("department", form.profileType === "faculty" ? form.department.trim() : "");
      formData.append("class_name", form.profileType === "student" ? form.className.trim() : "");
      formData.append("section_name", form.profileType === "student" ? form.sectionName.trim() : "");
      formData.append("roll_number", form.profileType === "student" ? form.rollNumber.trim() : "");
      FACE_VIEW_FIELDS.forEach((view) => {
        formData.append(`image_${view.key}`, imageFiles[view.key]);
      });
      if (!isStudent) {
        formData.append("check_in_time", form.checkInTime);
        formData.append("check_out_time", form.checkOutTime);
      }

      const result = await registerProfile(formData);
      setMessage(result.message || "Profile registered successfully.");
      setForm(buildInitialForm(location.search));
      setImageFiles({});
    } catch (error) {
      const usableViews = Array.isArray(error?.usable_views) && error.usable_views.length
        ? ` Usable views: ${error.usable_views.join(", ")}.`
        : "";
      const viewErrors = error?.view_errors
        ? Object.entries(error.view_errors).map(([viewName, viewMessage]) => `${viewName}: ${viewMessage}`).join(" ")
        : "";
      setMessage(`${error.message || "Unable to register profile."}${usableViews}${viewErrors ? ` ${viewErrors}` : ""}`);
    } finally {
      setSubmitting(false);
    }
  }

  const isStudent = form.profileType === "student";

  return (
    <AppShell
      title="Attendance registration"
      subtitle="Register faculty or student attendance profiles with guided multi-view face enrollment."
    >
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Registration</p>
          <h2>Choose the role first, then complete the right enrollment flow.</h2>
        </div>
      </section>

      <section className="registration-layout">
        <form className="panel registration-form" onSubmit={handleSubmit}>
          <h3>Profile setup</h3>

          <div className="report-mode-row" role="tablist" aria-label="Profile type">
            <button
              aria-pressed={form.profileType === "faculty"}
              className={`report-mode-button ${form.profileType === "faculty" ? "active" : ""}`}
              name="profileType"
              onClick={() => setForm((current) => ({ ...current, profileType: "faculty", className: "", sectionName: "", rollNumber: "" }))}
              type="button"
            >
              Faculty
            </button>
            <button
              aria-pressed={form.profileType === "student"}
              className={`report-mode-button ${form.profileType === "student" ? "active" : ""}`}
              name="profileType"
              onClick={() => setForm((current) => ({ ...current, profileType: "student", department: "" }))}
              type="button"
            >
              Student
            </button>
          </div>

          <div className="camera-form-grid">
            <label className="filter-field camera-form-wide">
              <span>Full name</span>
              <input name="name" onChange={updateField} value={form.name} />
            </label>

            <label className="filter-field">
              <span>Email</span>
              <input name="email" onChange={updateField} type="email" value={form.email} />
            </label>

            {isStudent ? (
              <>
                <label className="filter-field">
                  <span>Class</span>
                  <select name="className" onChange={updateField} value={form.className}>
                    <option value="">Select class</option>
                    {CLASS_OPTIONS.map((className) => (
                      <option key={className} value={className}>
                        {className}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="filter-field">
                  <span>Section</span>
                  <select
                    name="sectionName"
                    onChange={(event) => {
                      if (event.target.value === "__new__") {
                        setIsAddingSection(true);
                        setForm((current) => ({
                          ...current,
                          sectionName: ""
                        }));
                        return;
                      }

                      setIsAddingSection(false);
                      setNewSectionName("");
                      updateField(event);
                    }}
                    value={isAddingSection ? "__new__" : form.sectionName}
                  >
                    <option value="">Select section</option>
                    {sectionOptions.map((sectionName) => (
                      <option key={sectionName} value={sectionName}>
                        {sectionName}
                      </option>
                    ))}
                    <option value="__new__">Add new section</option>
                  </select>
                </label>
                {isAddingSection ? (
                  <div className="split-fields camera-form-wide">
                    <label className="filter-field">
                      <span>New section</span>
                      <input
                        onChange={(event) => setNewSectionName(event.target.value)}
                        placeholder="Enter section name"
                        value={newSectionName}
                      />
                    </label>
                    <div className="section-actions">
                      <button className="secondary-button" onClick={commitNewSection} type="button">
                        Save section
                      </button>
                    </div>
                  </div>
                ) : null}
                <label className="filter-field">
                  <span>Roll number</span>
                  <input name="rollNumber" onChange={updateField} value={form.rollNumber} />
                </label>
              </>
            ) : (
              <label className="filter-field">
                <span>Department</span>
                <input name="department" onChange={updateField} value={form.department} />
              </label>
            )}

            {!isStudent ? (
              <>
                <label className="filter-field">
                  <span>Check-in time</span>
                  <input name="checkInTime" onChange={updateField} type="time" value={form.checkInTime} />
                </label>
                <label className="filter-field">
                  <span>Check-out time</span>
                  <input name="checkOutTime" onChange={updateField} type="time" value={form.checkOutTime} />
                </label>
              </>
            ) : null}
            <div className="filter-field camera-form-wide">
              <span>Required face views</span>
              <p className="inline-note capture-help-text">
                Click <strong>Capture</strong> on any face view to request camera permission and save that pose directly.
              </p>
              {cameraError ? <p className="inline-note">{cameraError}</p> : null}
              {cameraOpen ? (
                <div className="camera-capture-panel">
                  <div className="capture-toolbar">
                    <div className="capture-session-copy">
                      Capturing for <strong>{FACE_VIEW_FIELDS.find((view) => view.key === selectedCaptureView)?.label}</strong>
                    </div>
                    <button className="primary-button" onClick={capturePhoto} type="button">
                      Capture photo
                    </button>
                    <button className="secondary-button" onClick={closeCamera} type="button">
                      Close camera
                    </button>
                  </div>
                  <div className="frame-preview">
                    <video autoPlay muted playsInline ref={videoRef} />
                    {!cameraReady ? <div className="camera-preview-placeholder">Loading camera preview...</div> : null}
                  </div>
                  <p className="inline-note">
                    Align the face for <strong>{FACE_VIEW_FIELDS.find((view) => view.key === selectedCaptureView)?.label}</strong>, then capture.
                  </p>
                </div>
              ) : null}
              <div className="multi-view-upload-grid">
                {FACE_VIEW_FIELDS.map((view) => (
                  <div className="capture-input-card" key={view.key}>
                    <div className="capture-card-header">
                      <span>{view.label}</span>
                      <span className={`status-pill ${imageFiles[view.key] ? "present" : "absent"}`}>
                        {imageFiles[view.key] ? "Captured" : "Pending"}
                      </span>
                    </div>
                    <label className="filter-field capture-upload-field">
                      <span>Upload image</span>
                      <input accept="image/*" onChange={(event) => updateFile(view.key, event)} type="file" />
                    </label>
                    <div className="capture-card-footer">
                      <button
                        className={`secondary-button ${selectedCaptureView === view.key ? "active-capture-button" : ""}`}
                        disabled={cameraLoading}
                        onClick={() => openCamera(view.key)}
                        type="button"
                      >
                        {cameraLoading && selectedCaptureView === view.key
                          ? "Opening..."
                          : cameraOpen && selectedCaptureView === view.key
                            ? "Capture active"
                            : "Capture"}
                      </button>
                      {imageFiles[view.key] ? (
                        <button
                          className="ghost-button"
                          onClick={() =>
                            setImageFiles((current) => ({
                              ...current,
                              [view.key]: null
                            }))
                          }
                          type="button"
                        >
                          Remove
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <canvas hidden ref={captureCanvasRef} />

          {message ? <p className="inline-note">{message}</p> : null}

          <div className="section-actions">
            <button className="primary-button" disabled={submitting} type="submit">
              {submitting ? "Registering..." : `Register ${isStudent ? "student" : "faculty"}`}
            </button>
          </div>
        </form>

        <aside className="panel registration-preview">
          <h3>Registration summary</h3>
          <div className="detail-stack">
            <div className="detail-card">
              <h4>{form.name || `New ${isStudent ? "student" : "faculty"} profile`}</h4>
              <p>{isStudent ? "Student profile" : "Faculty profile"}</p>
              <p>{form.email || "No email provided"}</p>
              {isStudent ? (
                <p>{[form.className || "Class -", form.sectionName || "Section -", form.rollNumber || "Roll -"].join(" · ")}</p>
              ) : (
                <p>{form.department || "No department provided"}</p>
              )}
            </div>
            {!isStudent ? (
              <div className="detail-card">
                <h4>Expected schedule</h4>
                <p>Check-in: {form.checkInTime}</p>
                <p>Check-out: {form.checkOutTime}</p>
              </div>
            ) : null}
            <div className="detail-card">
              <h4>Image preview</h4>
              <div className="multi-view-preview-grid">
                {FACE_VIEW_FIELDS.map((view) => (
                  <div className="detail-card" key={view.key}>
                    <h4>{view.label}</h4>
                    {previewUrls[view.key] ? (
                      <div className="frame-preview">
                        <img alt={`${view.label} preview`} src={previewUrls[view.key]} />
                      </div>
                    ) : (
                      <p className="inline-note">Pending capture</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </aside>
      </section>
    </AppShell>
  );
}
