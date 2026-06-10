/* ============================================================
   植物浇水签到系统 - 前端通用 JS
   ============================================================ */

(function () {
  "use strict";

  /* ========== 函数定义（先定义后使用） ========== */

  /* ---------- 1. Toast 提示 ---------- */
  window.showToast = function (message, type) {
    type = type || "success";
    var toast = document.getElementById("toast");
    if (!toast) return;

    toast.classList.remove("show", "success", "error");
    void toast.offsetWidth;

    toast.textContent = message;
    toast.classList.add(type, "show");

    clearTimeout(window._toastTimer);
    window._toastTimer = setTimeout(function () {
      toast.classList.remove("show");
    }, 2000);
  };

  /* ---------- 2. Modal 弹窗 ---------- */
  window.showModal = function (title, message, onConfirm) {
    var overlay = document.getElementById("modalOverlay");
    if (!overlay) return;

    var titleEl = overlay.querySelector(".modal-title");
    var msgEl = overlay.querySelector(".modal-message");
    var oldConfirm = overlay.querySelector(".modal-confirm");

    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;

    if (oldConfirm) {
      var newConfirm = oldConfirm.cloneNode(true);
      oldConfirm.parentNode.replaceChild(newConfirm, oldConfirm);

      newConfirm.addEventListener("click", function () {
        closeModal();
        if (typeof onConfirm === "function") {
          onConfirm();
        }
      });
    }

    overlay.classList.add("show");
  };

  /* ---------- 3. 关闭 Modal ---------- */
  window.closeModal = function () {
    var overlay = document.getElementById("modalOverlay");
    if (overlay) overlay.classList.remove("show");
  };

  /* ---------- 4. 全屏照片查看器（滑动 + 缩放） ---------- */
  var viewerPhotos = [];
  var viewerIndex = 0;
  var viewerScale = 1;
  var viewerTranslateX = 0;
  var viewerTranslateY = 0;
  var lastTapTime = 0;

  function getTrack() {
    return document.getElementById("viewerTrack");
  }

  function getBody() {
    return document.getElementById("viewerBody");
  }

  function setTrackPosition(offset, animate) {
    var track = getTrack();
    if (!track) return;
    if (animate) {
      track.classList.remove("dragging");
    } else {
      track.classList.add("dragging");
    }
    track.style.transform = "translateX(" + offset + "px)";
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function getActiveImage() {
    var track = getTrack();
    if (!track) return null;
    var slide = track.children[viewerIndex];
    return slide ? slide.querySelector("img") : null;
  }

  function applyImageTransform() {
    var img = getActiveImage();
    if (!img) return;
    img.style.transform = "translate(" + viewerTranslateX + "px, " + viewerTranslateY + "px) scale(" + viewerScale + ")";
    img.classList.toggle("zoomed", viewerScale > 1);
  }

  function resetZoom() {
    var track = getTrack();
    if (track) {
      track.querySelectorAll(".viewer-slide img").forEach(function (img) {
        img.style.transform = "";
        img.classList.remove("zoomed");
      });
    }
    viewerScale = 1;
    viewerTranslateX = 0;
    viewerTranslateY = 0;
  }

  function setZoom(scale, centerX, centerY) {
    var oldScale = viewerScale;
    viewerScale = clamp(scale, 1, 4);
    if (viewerScale === 1) {
      viewerTranslateX = 0;
      viewerTranslateY = 0;
    } else if (centerX !== undefined && centerY !== undefined && oldScale > 0) {
      var body = getBody();
      if (body) {
        var dx = centerX - body.clientWidth / 2;
        var dy = centerY - body.clientHeight / 2;
        var ratio = viewerScale / oldScale;
        viewerTranslateX = viewerTranslateX * ratio - dx * (ratio - 1);
        viewerTranslateY = viewerTranslateY * ratio - dy * (ratio - 1);
      }
    }
    applyImageTransform();
  }

  function buildSlides() {
    var track = getTrack();
    if (!track) return;
    track.innerHTML = "";
    viewerPhotos.forEach(function (src) {
      var slide = document.createElement("div");
      slide.className = "viewer-slide";
      var img = document.createElement("img");
      img.src = src;
      img.alt = "照片";
      img.draggable = false;
      slide.appendChild(img);
      track.appendChild(slide);
    });
  }

  function slideToIndex(index, animate) {
    var body = getBody();
    if (!body) return;
    resetZoom();
    viewerIndex = index;
    var offset = -viewerIndex * body.clientWidth;
    setTrackPosition(offset, animate !== false);
    updateCounter();
  }

  function updateCounter() {
    var counter = document.getElementById("viewerCounter");
    var prevBtn = document.getElementById("viewerPrev");
    var nextBtn = document.getElementById("viewerNext");
    if (counter) counter.textContent = (viewerIndex + 1) + " / " + viewerPhotos.length;
    if (prevBtn) prevBtn.disabled = viewerPhotos.length <= 1;
    if (nextBtn) nextBtn.disabled = viewerPhotos.length <= 1;
  }

  function showViewer() {
    var overlay = document.getElementById("viewerOverlay");
    if (!overlay || viewerPhotos.length === 0) return;
    buildSlides();
    overlay.classList.add("show");
    resetZoom();
    // 等 DOM 渲染后再定位，避免动画错位
    requestAnimationFrame(function () {
      slideToIndex(viewerIndex, false);
    });
    document.body.style.overflow = "hidden";
  }

  window.closeViewer = function () {
    var overlay = document.getElementById("viewerOverlay");
    if (overlay) overlay.classList.remove("show");
    document.body.style.overflow = "";
  };

  window.viewerPrev = function () {
    if (viewerIndex > 0) slideToIndex(viewerIndex - 1, true);
  };

  window.viewerNext = function () {
    if (viewerIndex < viewerPhotos.length - 1) slideToIndex(viewerIndex + 1, true);
  };

  window.openViewerFromUrls = function (urls, index) {
    viewerPhotos = (urls || []).filter(Boolean);
    viewerIndex = index || 0;
    if (viewerIndex < 0 || viewerIndex >= viewerPhotos.length) viewerIndex = 0;
    showViewer();
  };

  window.openViewer = function (imgElement) {
    var recordItem = imgElement.closest(".record-item") || imgElement.closest(".cal-detail-item");
    if (!recordItem) return;

    var thumbs = recordItem.querySelectorAll("img[class*='thumb']");
    viewerPhotos = [];
    thumbs.forEach(function (thumb) {
      var src = thumb.getAttribute("src") || thumb.dataset.src;
      if (src) viewerPhotos.push(src);
    });

    var clickedSrc = imgElement.getAttribute("src") || imgElement.dataset.src;
    viewerIndex = viewerPhotos.indexOf(clickedSrc);
    if (viewerIndex === -1) viewerIndex = 0;

    showViewer();
  };

  window.openViewerUrl = function (url) {
    var imgEl = document.querySelector('img[src="' + url + '"]');
    if (imgEl) {
      var photoGroup = imgEl.closest(".photo-group");
      if (photoGroup) {
        var items = photoGroup.querySelectorAll(".photo-item img");
        viewerPhotos = [];
        items.forEach(function (item) {
          var src = item.getAttribute("src");
          if (src) viewerPhotos.push(src);
        });
        viewerIndex = viewerPhotos.indexOf(url);
        if (viewerIndex === -1) viewerIndex = 0;
        showViewer();
        return;
      }
    }

    if (imgEl) {
      var recordItem = imgEl.closest(".record-item");
      var calDetailItem = imgEl.closest(".cal-detail-item");
      var container = recordItem || calDetailItem;

      if (container) {
        var thumbs = container.querySelectorAll("img[class*='thumb']");
        if (thumbs.length > 0) {
          viewerPhotos = [];
          thumbs.forEach(function (thumb) {
            var src = thumb.getAttribute("src");
            if (src) viewerPhotos.push(src);
          });
          viewerIndex = viewerPhotos.indexOf(url);
          if (viewerIndex === -1) viewerIndex = 0;
          showViewer();
          return;
        }
      }
    }

    viewerPhotos = [url];
    viewerIndex = 0;
    showViewer();
  };

  /* ---------- 5. 设置面板 ---------- */
  window.openSettings = function () {
    var overlay = document.getElementById("settingsOverlay");
    if (overlay) {
      overlay.classList.add("show");
      document.body.style.overflow = "hidden";
    }
  };

  window.closeSettings = function () {
    var overlay = document.getElementById("settingsOverlay");
    if (overlay) {
      overlay.classList.remove("show");
      document.body.style.overflow = "";
    }
  };

  /* ========== 初始化（在所有函数定义之后） ========== */

  /* ---------- I1. 水滴动画初始化 ---------- */
  (function initDroplets() {
    var container = document.querySelector(".droplets");
    if (!container) return;

    var DROP_COUNT = 15;

    for (var i = 0; i < DROP_COUNT; i++) {
      var drop = document.createElement("div");
      drop.classList.add("drop");

      var size = Math.random() * 6 + 4;
      var left = Math.random() * 100;
      var duration = Math.random() * 4 + 3;
      var delay = Math.random() * 5;

      drop.style.width = size + "px";
      drop.style.height = (size * 1.5) + "px";
      drop.style.left = left + "%";
      drop.style.animationDuration = duration + "s";
      drop.style.animationDelay = delay + "s";

      container.appendChild(drop);
    }
  })();

  /* ---------- I2. Modal 取消按钮 ---------- */
  (function initModalCancel() {
    var cancelBtn = document.getElementById("modalCancelBtn");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        closeModal();
      });
    }
  })();

  /* ---------- I3. 点击遮罩关闭 ---------- */
  (function initOverlayClose() {
    var modalOverlay = document.getElementById("modalOverlay");
    if (modalOverlay) {
      modalOverlay.addEventListener("click", function (e) {
        if (e.target === modalOverlay) {
          closeModal();
        }
      });
    }

    var settingsOverlay = document.getElementById("settingsOverlay");
    if (settingsOverlay) {
      settingsOverlay.addEventListener("click", function (e) {
        if (e.target === settingsOverlay) {
          closeSettings();
        }
      });
    }
  })();

  /* ---------- I4. 查看器按钮事件 ---------- */
  (function initViewerButtons() {
    var closeBtn = document.getElementById("viewerClose");
    if (closeBtn) {
      closeBtn.addEventListener("click", closeViewer);
    }
    var prevBtn = document.getElementById("viewerPrev");
    if (prevBtn) {
      prevBtn.addEventListener("click", viewerPrev);
    }
    var nextBtn = document.getElementById("viewerNext");
    if (nextBtn) {
      nextBtn.addEventListener("click", viewerNext);
    }
  })();

  /* ---------- I5. 查看器手势：滑动、拖动、双指缩放、双击缩放 ---------- */
  (function initViewerTouch() {
    var overlay = document.getElementById("viewerOverlay");
    var body = getBody();
    if (!overlay || !body) return;

    var startX = 0;
    var startY = 0;
    var dragOffset = 0;
    var isDragging = false;
    var isHorizontal = null;
    var gestureMode = "";
    var panStartX = 0;
    var panStartY = 0;
    var panBaseX = 0;
    var panBaseY = 0;
    var pinchStartDistance = 0;
    var pinchStartScale = 1;

    function getDistance(t1, t2) {
      var dx = t1.clientX - t2.clientX;
      var dy = t1.clientY - t2.clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }

    function getMidpoint(t1, t2) {
      return {
        x: (t1.clientX + t2.clientX) / 2,
        y: (t1.clientY + t2.clientY) / 2
      };
    }

    overlay.addEventListener("touchstart", function (e) {
      if (e.touches.length === 2) {
        gestureMode = "pinch";
        pinchStartDistance = getDistance(e.touches[0], e.touches[1]);
        pinchStartScale = viewerScale;
        isDragging = false;
        return;
      }

      startX = e.changedTouches[0].clientX;
      startY = e.changedTouches[0].clientY;
      dragOffset = 0;
      isDragging = true;
      isHorizontal = null;
      gestureMode = viewerScale > 1 ? "pan" : "swipe";
      panStartX = startX;
      panStartY = startY;
      panBaseX = viewerTranslateX;
      panBaseY = viewerTranslateY;
    }, { passive: true });

    overlay.addEventListener("touchmove", function (e) {
      if (gestureMode === "pinch" && e.touches.length >= 2) {
        e.preventDefault();
        var midpoint = getMidpoint(e.touches[0], e.touches[1]);
        var nextScale = pinchStartScale * (getDistance(e.touches[0], e.touches[1]) / Math.max(pinchStartDistance, 1));
        setZoom(nextScale, midpoint.x, midpoint.y);
        return;
      }

      if (!isDragging || e.touches.length !== 1) return;

      var dx = e.changedTouches[0].clientX - startX;
      var dy = e.changedTouches[0].clientY - startY;

      if (gestureMode === "pan") {
        e.preventDefault();
        viewerTranslateX = panBaseX + (e.changedTouches[0].clientX - panStartX);
        viewerTranslateY = panBaseY + (e.changedTouches[0].clientY - panStartY);
        applyImageTransform();
        return;
      }

      if (isHorizontal === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
        isHorizontal = Math.abs(dx) > Math.abs(dy);
      }
      if (!isHorizontal) return;
      e.preventDefault();

      // 基准位置 + 拖拽偏移
      var baseOffset = -viewerIndex * body.clientWidth;
      dragOffset = dx;

      // 边缘阻力
      if ((viewerIndex === 0 && dx > 0) || (viewerIndex === viewerPhotos.length - 1 && dx < 0)) {
        dragOffset = dx * 0.3;
      }

      setTrackPosition(baseOffset + dragOffset, false);
    }, { passive: false });

    overlay.addEventListener("touchend", function () {
      if (gestureMode === "pinch") {
        if (viewerScale <= 1.02) resetZoom();
        gestureMode = "";
        return;
      }

      if (gestureMode === "pan") {
        if (viewerScale <= 1.02) resetZoom();
        gestureMode = "";
        isDragging = false;
        return;
      }

      if (!isDragging) return;
      isDragging = false;

      var threshold = body.clientWidth * 0.2; // 滑过20%宽度即切换

      if (dragOffset < -threshold && viewerIndex < viewerPhotos.length - 1) {
        slideToIndex(viewerIndex + 1, true);
      } else if (dragOffset > threshold && viewerIndex > 0) {
        slideToIndex(viewerIndex - 1, true);
      } else {
        // 回弹到当前
        slideToIndex(viewerIndex, true);
      }
      gestureMode = "";
    }, { passive: true });

    overlay.addEventListener("dblclick", function (e) {
      if (!e.target || e.target.tagName !== "IMG") return;
      if (viewerScale > 1) {
        resetZoom();
      } else {
        setZoom(2, e.clientX, e.clientY);
      }
    });
  })();

  /* ---------- I6. 键盘支持 ---------- */
  (function initKeyboard() {
    document.addEventListener("keydown", function (e) {
      var viewerOverlay = document.getElementById("viewerOverlay");
      var modalOverlay = document.getElementById("modalOverlay");
      var settingsOverlay = document.getElementById("settingsOverlay");

      if (e.key === "Escape") {
        if (viewerOverlay && viewerOverlay.classList.contains("show")) {
          closeViewer();
          return;
        }
        if (modalOverlay && modalOverlay.classList.contains("show")) {
          closeModal();
          return;
        }
        if (settingsOverlay && settingsOverlay.classList.contains("show")) {
          closeSettings();
          return;
        }
      }

      if (viewerOverlay && viewerOverlay.classList.contains("show")) {
        if (e.key === "ArrowLeft") {
          e.preventDefault();
          viewerPrev();
        } else if (e.key === "ArrowRight") {
          e.preventDefault();
          viewerNext();
        }
      }
    });
  })();

  /* ---------- I7. 设置关闭按钮 ---------- */
  (function initSettingsClose() {
    var closeBtn = document.getElementById("settingsClose");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        closeSettings();
      });
    }
  })();

})();
