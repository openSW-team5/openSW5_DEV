window.ToastHelper = {
  success: function(text) {
    Toastify({
      text: text,
      duration: 3000,
      close: true,
      gravity: "top",
      position: "center",
      style: {
        background: "#4CAF50",
      },
      className: "font-yidstreet",
      stopOnFocus: true,
    }).showToast();
  },
  error: function(text) {
    Toastify({
      text: text,
      duration: 3000,
      close: true,
      gravity: "top",
      position: "center",
      style: {
        background: "#F44336",
      },
      className: "font-yidstreet",
      stopOnFocus: true,
    }).showToast();
  },
  warning: function(text) {
    Toastify({
      text: text,
      duration: 3000,
      close: true,
      gravity: "top",
      position: "center",
      style: {
        background: "#FF9800",
      },
      className: "font-yidstreet",
      stopOnFocus: true,
    }).showToast();
  },
  info: function(text) {
    Toastify({
      text: text,
      duration: 3000,
      close: true,
      gravity: "top",
      position: "center",
      style: {
        background: "#2196F3",
      },
      className: "font-yidstreet",
      stopOnFocus: true,
    }).showToast();
  }
};
