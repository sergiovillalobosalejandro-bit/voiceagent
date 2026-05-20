import { useState, useRef, useEffect } from "react";

const API_URL =
  import.meta.env.VITE_API_URL || "https://soundbot-backend.onrender.com";
const SESSION_ID = "soundbot-" + Math.random().toString(36).slice(2, 9);

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
  const [micError, setMicError] = useState(null);
  const chatEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const fileInputRef = useRef(null);
  const audioInputRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (messages.length === 0) {
      setMessages([{
        role: "assistant",
        content: "Bienvenido a SoundBot. Preguntame sobre instrumentos, afinacion o teoria musical. / Welcome to SoundBot. Ask me about instruments, tuning, or music theory.",
        tool_used: null,
        cache_hit: false,
      }]);
    }
  }, []);

  const toBase64 = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const getSupportedMimeType = () => {
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4", "audio/wav"];
    for (const t of types) if (MediaRecorder.isTypeSupported(t)) return t;
    return "";
  };

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
    } catch {
      setMicError("MIC ACCESS DENIED");
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

  const handleImageSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImageFile(file);
    setImagePreview(URL.createObjectURL(file));
  };

  const removeImage = () => {
    setImageFile(null);
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImagePreview(null);
  };

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
        const res = await fetch(`${API_URL}/voice/chat`, { method: "POST", body: formData });
        const data = await res.json();
        setMessages((prev) => [...prev,
          { role: "user", content: "[VOICE MESSAGE]", voice: true },
          { role: "assistant", content: data.answer, tool_used: data.tool_used, cache_hit: data.cache_hit, language: data.language, audio_base64: data.audio_base64 },
        ]);
      } catch {
        setMessages((prev) => [...prev,
          { role: "assistant", content: "Maldita sea, choom. Algo se jodio en la red.", tool_used: null, cache_hit: false },
        ]);
      } finally {
        setLoading(false);
        setAudioBlob(null);
      }
      return;
    }

    const userContent = inputMode === "image" && imageFile ? (input.trim() || "[IMAGE ATTACHED]") : input.trim();

    setMessages((prev) => [...prev,
      { role: "user", content: userContent, image_preview: imagePreview },
    ]);
    setInput("");
    setLoading(true);

    const body = { session_id: SESSION_ID, message: userContent, output_audio: outputAudio };
    if (inputMode === "image" && imageFile) body.image_base64 = await toBase64(imageFile);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      setMessages((prev) => [...prev,
        { role: "assistant", content: data.answer, tool_used: data.tool_used, cache_hit: data.cache_hit, language: data.language, audio_base64: data.audio_base64 },
      ]);
    } catch {
      setMessages((prev) => [...prev,
        { role: "assistant", content: "Maldita sea, choom. Algo se jodio en la red.", tool_used: null, cache_hit: false },
      ]);
    } finally {
      setLoading(false);
      setImageFile(null);
      setImagePreview(null);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const AudioPlayer = ({ base64 }) => (
    <audio controls className="audio-player">
      <source src={`data:audio/mp3;base64,${base64}`} type="audio/mp3" />
    </audio>
  );

  return (
    <>
      <div className="scanlines"></div>
      <div className="chat-container">
        <div className="chat-wrapper">
          <div className="corner-decor tl"></div>
          <div className="corner-decor tr"></div>
          <div className="corner-decor bl"></div>
          <div className="corner-decor br"></div>

          <div className="header">
            <div className="header-top">
              <div className="header-icon">
                <svg viewBox="0 0 24 24">
                  <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
                </svg>
              </div>
              <div className="header-info">
                <h1>SOUNDBOT</h1>
                <div className="subtitle">// Music AI · Instruments & Theory</div>
              </div>
              <div className="header-status">
                <div className="dot"></div>
                ONLINE
              </div>
            </div>
            <div className="header-bar">
              <span>CHANNEL: <span className="val">{inputMode.toUpperCase()}</span></span>
              <span>OUTPUT: <span className="val">{outputAudio ? "AUDIO" : "TEXT"}</span></span>
              <span>MEM: <span className="val">{Math.min(messages.length, 14)}</span></span>
            </div>
          </div>

          <div className="chat-messages">
            {messages.map((msg, i) => (
              <div key={i} className={`message-row ${msg.role}`}>
                <div className={`avatar ${msg.role === "user" ? "user-avatar" : "bot"}`}>
                  {msg.role === "user" ? "V" : "SB"}
                </div>
                <div className={`bubble ${msg.role === "user" ? "user-bubble" : "bot"}`}>
                  <div className="sender">
                    {msg.role === "user" ? "YOU" : "SOUNDBOT"}
                  </div>
                  {msg.image_preview && (
                    <img src={msg.image_preview} alt="upload" className="msg-image" />
                  )}
                  {msg.voice && (
                    <div className="voice-indicator">[VOICE INPUT]</div>
                  )}
                  <div className="msg-text">{msg.content}</div>
                  {msg.audio_base64 && <AudioPlayer base64={msg.audio_base64} />}
                  {(msg.tool_used || msg.cache_hit) && (
                    <div style={{marginTop: 6}}>
                      {msg.tool_used && <span className="badge badge-tool">{msg.tool_used}</span>}
                      {msg.cache_hit && <span className="badge badge-cache">CACHED</span>}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="typing-indicator">
                SOUNDBOT <span className="dots"><span></span><span></span><span></span></span>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          <div className="input-area">
            {inputMode === "image" && (
              <div className="image-upload-area" style={{padding: "0 8px"}}>
                {imagePreview ? (
                  <div className="image-preview-wrap">
                    <img src={imagePreview} alt="preview" />
                    <button className="remove-img-btn" onClick={removeImage}>X</button>
                  </div>
                ) : (
                  <button className="ctrl-btn" onClick={() => fileInputRef.current?.click()}>+IMG</button>
                )}
                <input ref={fileInputRef} type="file" accept="image/*" hidden onChange={handleImageSelect} />
              </div>
            )}

            {inputMode === "voice" && (
              <div className="voice-input-area" style={{padding: "0 8px"}}>
                {micError && <span className="mic-error">{micError}</span>}
                {audioBlob ? (
                  <div className="voice-ready">
                    AUDIO {Math.round(audioBlob.size / 1024)}KB
                    <button className="ctrl-btn" onClick={() => setAudioBlob(null)}>X</button>
                  </div>
                ) : recording ? (
                  <button className="ctrl-btn" onClick={stopRecording} style={{borderColor: "var(--cyber-red)", color: "var(--cyber-red)"}}>STOP REC</button>
                ) : (
                  <div className="voice-actions">
                    <button className="ctrl-btn" onClick={startRecording}>REC</button>
                    <button className="ctrl-btn" onClick={() => audioInputRef.current?.click()}>FILE</button>
                    <input ref={audioInputRef} type="file" accept="audio/*" hidden onChange={handleAudioFile} />
                  </div>
                )}
              </div>
            )}

            {(inputMode === "text" || inputMode === "image") && (
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="> Escribe tu mensaje..."
                rows={1}
                disabled={loading}
              />
            )}

            <button
              className="send-btn"
              onClick={sendMessage}
              disabled={loading ||
                (inputMode === "voice" ? !audioBlob : inputMode === "image" ? !imageFile && !input.trim() : !input.trim())
              }
            >
              [ SEND ]
            </button>
          </div>

          <div className="controls-bar">
            <span>INPUT:</span>
            {[["text", "TEXT"], ["voice", "VOICE"], ["image", "IMG+TXT"]].map(([mode, label]) => (
              <button
                key={mode}
                className={`ctrl-btn ${inputMode === mode ? "active" : ""}`}
                onClick={() => { setInputMode(mode); setImageFile(null); setImagePreview(null); setAudioBlob(null); }}
              >
                {label}
              </button>
            ))}
            <span style={{marginLeft: 12}}>OUTPUT:</span>
            <button
              className={`ctrl-btn ${outputAudio ? "active" : ""}`}
              onClick={() => setOutputAudio(!outputAudio)}
            >
              {outputAudio ? "AUDIO" : "TEXT"}
            </button>
          </div>
        </div>
        <div className="watermark">// SOUNDBOT · MUSIC AI · 2077 //</div>
      </div>
    </>
  );
}

export default App;
