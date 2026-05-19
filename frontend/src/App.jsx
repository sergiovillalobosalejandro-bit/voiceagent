import { useState, useRef, useEffect } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const SESSION_ID =
  "finbot-session-" + Math.random().toString(36).slice(2, 9);

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [inputMode, setInputMode] = useState("text");
  const [outputAudio, setOutputAudio] = useState(false);
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [audioBlob, setAudioBlob] = useState(null);
  const [recording, setRecording] = useState(false);
  const chatEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const fileInputRef = useRef(null);
  const audioInputRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const toBase64 = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const sendMessage = async () => {
    const hasText = input.trim().length > 0;
    const hasImage = inputMode === "image" && imageFile;
    const hasAudio = inputMode === "voice" && audioBlob;

    if (!hasText && !hasImage && !hasAudio) return;
    if (loading) return;

    if (inputMode === "voice" && audioBlob) {
      setLoading(true);
      const formData = new FormData();
      formData.append("audio", audioBlob, "recording.webm");
      formData.append("session_id", SESSION_ID);
      formData.append("output_audio", outputAudio.toString());

      try {
        const res = await fetch(`${API_URL}/voice/chat`, {
          method: "POST",
          body: formData,
        });
        const data = await res.json();

        setMessages((prev) => [
          ...prev,
          { role: "user", content: "[Mensaje de voz]", voice: true },
          {
            role: "assistant",
            content: data.answer,
            tool_used: data.tool_used,
            cache_hit: data.cache_hit,
            language: data.language,
            audio_base64: data.audio_base64,
          },
        ]);
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Error: No se pudo conectar con el servidor.",
            tool_used: null,
            cache_hit: false,
          },
        ]);
      } finally {
        setLoading(false);
        setAudioBlob(null);
      }
      return;
    }

    const userContent =
      inputMode === "image" && imageFile
        ? input.trim() || "[Imagen adjunta]"
        : input.trim();

    setMessages((prev) => [
      ...prev,
      { role: "user", content: userContent, image_preview: imagePreview },
    ]);
    setInput("");
    setLoading(true);

    const body = {
      session_id: SESSION_ID,
      message: userContent,
      output_audio: outputAudio,
    };

    if (inputMode === "image" && imageFile) {
      body.image_base64 = await toBase64(imageFile);
    }

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await res.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          tool_used: data.tool_used,
          cache_hit: data.cache_hit,
          language: data.language,
          audio_base64: data.audio_base64,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Error: No se pudo conectar con el servidor.",
          tool_used: null,
          cache_hit: false,
        },
      ]);
    } finally {
      setLoading(false);
      setImageFile(null);
      setImagePreview(null);
    }
  };

  const handleImageSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImageFile(file);
    const url = URL.createObjectURL(file);
    setImagePreview(url);
  };

  const removeImage = () => {
    setImageFile(null);
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImagePreview(null);
  };

  const getSupportedMimeType = () => {
    const types = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/mp4",
      "audio/wav",
    ];
    for (const t of types) {
      if (MediaRecorder.isTypeSupported(t)) return t;
    }
    return "";
  };

  const [micError, setMicError] = useState(null);

  const startRecording = async () => {
    setMicError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = getSupportedMimeType();
      const opts = mimeType ? { mimeType } : {};
      const recorder = new MediaRecorder(stream, opts);
      const chunks = [];
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = () => {
        setAudioBlob(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
        stream.getTracks().forEach((t) => t.stop());
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      setMicError("Micrófono no disponible. Permití el acceso al micrófono o usá 'Subir audio'.");
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  const handleAudioFile = (e) => {
    const file = e.target.files?.[0];
    if (file) setAudioBlob(file);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const AudioPlayer = ({ base64 }) => {
    const src = `data:audio/mp3;base64,${base64}`;
    return (
      <audio controls className="audio-player">
        <source src={src} type="audio/mp3" />
      </audio>
    );
  };

  return (
    <div className="chat-container">
      <header className="chat-header">
        <h1>
          <span className="logo">FinBot</span>
        </h1>
        <p>Asistente financiero · Colombia & USA</p>
      </header>

      <div className="mode-bar">
        <div className="mode-group">
          <span className="mode-label">Entrada:</span>
          {[
            ["text", "Texto"],
            ["voice", "Voz"],
            ["image", "Imagen+Texto"],
          ].map(([mode, label]) => (
            <button
              key={mode}
              className={`mode-btn ${inputMode === mode ? "active" : ""}`}
              onClick={() => {
                setInputMode(mode);
                setImageFile(null);
                setImagePreview(null);
                setAudioBlob(null);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="mode-group">
          <span className="mode-label">Salida:</span>
          <button
            className={`mode-btn ${outputAudio ? "active" : ""}`}
            onClick={() => setOutputAudio(!outputAudio)}
          >
            {outputAudio ? "Audio" : "Texto"}
          </button>
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="welcome">
            <p>Bienvenido a FinBot. ¿En qué puedo ayudarle hoy?</p>
            <p>Welcome to FinBot. How can I help you today?</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="message-role">
              {msg.role === "user" ? "Tú" : "FinBot"}
            </div>
            {msg.image_preview && (
              <img
                src={msg.image_preview}
                alt="upload"
                className="msg-image"
              />
            )}
            {msg.voice && (
              <div className="voice-indicator">🎤 Mensaje de voz</div>
            )}
            <div className="message-content">{msg.content}</div>
            {msg.audio_base64 && <AudioPlayer base64={msg.audio_base64} />}
            <div className="message-meta">
              {msg.tool_used && (
                <span className="badge badge-tool">{msg.tool_used}</span>
              )}
              {msg.cache_hit && (
                <span className="badge badge-cache">Cache</span>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="message assistant">
            <div className="message-role">FinBot</div>
            <div className="message-content typing">Escribiendo...</div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      <div className="chat-input-area">
        {inputMode === "image" && (
          <div className="image-upload-area">
            {imagePreview ? (
              <div className="image-preview-wrap">
                <img src={imagePreview} alt="preview" />
                <button className="remove-img-btn" onClick={removeImage}>
                  x
                </button>
              </div>
            ) : (
              <button
                className="upload-btn"
                onClick={() => fileInputRef.current?.click()}
              >
                + Imagen
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              hidden
              onChange={handleImageSelect}
            />
          </div>
        )}

        {inputMode === "voice" && (
          <div className="voice-input-area">
            {micError && <div className="mic-error">{micError}</div>}
            {audioBlob ? (
              <div className="voice-ready">
                Audio listo ({Math.round(audioBlob.size / 1024)} KB)
                <button
                  className="remove-img-btn"
                  onClick={() => setAudioBlob(null)}
                >
                  x
                </button>
              </div>
            ) : recording ? (
              <button className="record-btn recording" onClick={stopRecording}>
                Detener grabación
              </button>
            ) : (
              <div className="voice-actions">
                <button className="record-btn" onClick={startRecording}>
                  Grabar
                </button>
                <button
                  className="upload-btn"
                  onClick={() => audioInputRef.current?.click()}
                >
                  Subir audio
                </button>
                <input
                  ref={audioInputRef}
                  type="file"
                  accept="audio/*"
                  hidden
                  onChange={handleAudioFile}
                />
              </div>
            )}
          </div>
        )}

        {(inputMode === "text" || inputMode === "image") && (
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              inputMode === "image"
                ? "Describe la imagen (opcional)..."
                : "Escribe tu mensaje..."
            }
            rows={1}
            disabled={loading}
          />
        )}

        <button
          onClick={sendMessage}
          disabled={
            loading ||
            (inputMode === "voice"
              ? !audioBlob
              : inputMode === "image"
              ? !imageFile && !input.trim()
              : !input.trim())
          }
        >
          Enviar
        </button>
      </div>
    </div>
  );
}

export default App;
