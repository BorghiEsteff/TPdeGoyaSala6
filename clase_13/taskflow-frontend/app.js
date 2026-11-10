const API_URL = "https://tpdegoyasala6.onrender.com/api";
const WS_URL = "wss://tpdegoyasala6.onrender.com/ws";

let accessToken = sessionStorage.getItem("taskflow_token") || null;
let currentUsername = sessionStorage.getItem("taskflow_user") || "";
let activeSocket = null;
let reconnectTimer = null;
let currentProjectId = null;

function authHeaders() {
  return { Authorization: `Bearer ${accessToken}` };
}

async function login() {
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const errorBox = document.getElementById("login-error");
  errorBox.textContent = "";

  if (!username || !password) {
    errorBox.textContent = "Ingrese usuario y contraseña.";
    return;
  }

  try {
    const response = await fetch(`${API_URL}/token/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!response.ok) {
      errorBox.textContent =
        response.status === 429
          ? "Demasiados intentos. Esperen un minuto."
          : "Usuario o contraseña incorrectos.";
      return;
    }

    const data = await response.json();
    accessToken = data.access;
    currentUsername = username;
    sessionStorage.setItem("taskflow_token", accessToken);
    sessionStorage.setItem("taskflow_user", currentUsername);

    mostrarApp();
  } catch (err) {
    errorBox.textContent = "Error de red al conectar con el servidor.";
  }
}

function logout() {
  accessToken = null;
  currentUsername = "";
  sessionStorage.removeItem("taskflow_token");
  sessionStorage.removeItem("taskflow_user");

  if (activeSocket) {
    activeSocket.close();
    activeSocket = null;
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  document.getElementById("login-box").style.display = "block";
  document.getElementById("app-box").style.display = "none";
  document.getElementById("username").value = "";
  document.getElementById("password").value = "";
}

function mostrarApp() {
  document.getElementById("login-box").style.display = "none";
  document.getElementById("app-box").style.display = "block";
  document.getElementById("user-display").textContent = `Usuario: ${currentUsername}`;

  loadProjects().then(() => {
    loadTasks();
    const select = document.getElementById("project");
    if (select.value) {
      conectarWebSocket(select.value);
    }
  });
}

async function loadProjects() {
  try {
    const response = await fetch(`${API_URL}/projects/`, { headers: authHeaders() });
    if (!response.ok) {
      if (response.status === 401) logout();
      return;
    }

    const data = await response.json();
    const select = document.getElementById("project");
    select.innerHTML = "";

    const projects = data.results || data;
    projects.forEach((project) => {
      const option = document.createElement("option");
      option.value = project.id;
      option.textContent = project.name;
      select.appendChild(option);
    });
  } catch (err) {
    console.error("Error al cargar proyectos:", err);
  }
}

async function loadTasks() {
  try {
    const response = await fetch(`${API_URL}/tasks/`, { headers: authHeaders() });
    if (!response.ok) {
      if (response.status === 401) logout();
      return;
    }

    const data = await response.json();
    const list = document.getElementById("tasks");
    list.innerHTML = "";

    const tasks = data.results || data;
    if (tasks.length === 0) {
      const li = document.createElement("li");
      li.textContent = "No hay tareas registradas.";
      li.style.color = "#888";
      list.appendChild(li);
      return;
    }

    tasks.forEach((task) => {
      const li = document.createElement("li");

      const titleSpan = document.createElement("span");
      titleSpan.textContent = task.title;

      const badgeSpan = document.createElement("span");
      badgeSpan.className = `badge ${task.status}`;
      badgeSpan.textContent = task.status.replace("_", " ");

      li.appendChild(titleSpan);
      li.appendChild(badgeSpan);
      list.appendChild(li);
    });
  } catch (err) {
    console.error("Error al cargar tareas:", err);
  }
}

async function createTask() {
  const titleInput = document.getElementById("new-title");
  const title = titleInput.value.trim();
  const project = document.getElementById("project").value;
  const errorBox = document.getElementById("app-error");
  errorBox.textContent = "";

  if (!title || !project) {
    errorBox.textContent = "Complete el título de la tarea.";
    return;
  }

  try {
    const response = await fetch(`${API_URL}/tasks/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ title, project: Number(project) }),
    });

    if (!response.ok) {
      const data = await response.json();
      errorBox.textContent = data.detail || JSON.stringify(data);
      return;
    }

    titleInput.value = "";
    loadTasks();
  } catch (err) {
    errorBox.textContent = "Error al intentar crear la tarea.";
  }
}

function cambiarProyecto() {
  const select = document.getElementById("project");
  if (select.value) {
    conectarWebSocket(select.value);
  }
}

// Conexión en tiempo real por WebSocket (Clase 10 & Tarea opcional Clase 13)
function conectarWebSocket(projectId) {
  if (currentProjectId === projectId && activeSocket && activeSocket.readyState === WebSocket.OPEN) {
    return;
  }

  currentProjectId = projectId;
  if (activeSocket) {
    activeSocket.close();
    activeSocket = null;
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  const wsDot = document.getElementById("ws-dot");
  const wsStatus = document.getElementById("ws-status");
  let espera = 1000;
  let cerradoManual = false;

  function abrir() {
    if (!accessToken) return;
    const socket = new WebSocket(`${WS_URL}/projects/${projectId}/?token=${accessToken}`);
    activeSocket = socket;

    socket.onopen = () => {
      espera = 1000;
      wsDot.classList.add("active");
      wsStatus.textContent = `En vivo: Proyecto #${projectId}`;
      loadTasks(); // Sincronización al reconectar (Clase 10)
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        console.log("WebSocket event recibido:", payload);

        // Si es un evento de tareas, recargar la lista en vivo
        if (payload.event === "task_created" || payload.event === "task_updated" || payload.event === "task_completed") {
          loadTasks();
        }
      } catch (e) {
        console.warn("Mensaje no parseable:", event.data);
      }
    };

    socket.onclose = () => {
      wsDot.classList.remove("active");
      wsStatus.textContent = "Reconectando WebSocket...";
      if (cerradoManual || !accessToken) return;

      const jitter = Math.random() * 500;
      const demora = espera + jitter;
      reconnectTimer = setTimeout(abrir, demora);
      espera = Math.min(espera * 2, 30000);
    };

    socket.onerror = (err) => {
      console.warn("WebSocket error:", err);
      socket.close();
    };
  }

  abrir();
}

// Iniciar automáticamente si ya estaba logueado
window.addEventListener("DOMContentLoaded", () => {
  if (accessToken) {
    mostrarApp();
  }
});

