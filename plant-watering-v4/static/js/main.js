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

  /* ---------- 4. 全屏照片查看器（轨道滑动） ---------- */
  var viewerPhotos = [];
  var viewerIndex = 0;
  // 照片URL到照片ID的映射（用于全屏查看器中编辑标签/注释）
  var viewerPhotoIds = {};

  // 暴露 viewerIndex 的只读访问接口（供 records.html 留言功能使用）
  Object.defineProperty(window, 'viewerIndex', {
    get: function () { return viewerIndex; },
    set: function (val) { viewerIndex = val; }
  });

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

  function buildSlides() {
    var track = getTrack();
    if (!track) return;
    track.innerHTML = "";
    viewerPhotos.forEach(function (src, idx) {
      var slide = document.createElement("div");
      slide.className = "viewer-slide";
      var img = document.createElement("img");
      img.src = src;
      img.alt = "照片";
      img.draggable = false;
      img.setAttribute("data-index", idx);
      slide.appendChild(img);
      track.appendChild(slide);
    });
  }

  function slideToIndex(index, animate) {
    var body = getBody();
    if (!body) return;
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
    // 关闭查看器时同时关闭注释编辑器
    closeCaptionEditor();
  };

  /* ---------- 4a. 获取当前查看照片的ID ---------- */
  function getCurrentViewerPhotoId() {
    var src = viewerPhotos[viewerIndex];
    return viewerPhotoIds[src] || null;
  }

  /* ---------- 4b. 编辑标签（全屏查看器内） ---------- */
  function handleViewerEditTags() {
    var photoId = getCurrentViewerPhotoId();
    if (!photoId) {
      showToast("无法获取照片信息", "error");
      return;
    }
    // 先通过API获取当前照片的tags，用于预选
    fetch("/api/photos/" + photoId)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var existingIds = [];
        if (data.tags && Array.isArray(data.tags)) {
          existingIds = data.tags.map(function (t) { return t.id || t.tag_id; });
        }
        // 打开Tag选择弹层，预选已有tags
        openTagPicker(existingIds, function (selectedIds) {
          // 用户确认后，调用API保存
          fetch("/api/photos/" + photoId + "/tags", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tag_ids: selectedIds })
          })
            .then(function (r) { return r.json(); })
            .then(function (result) {
              if (result.success) {
                showToast("标签已更新");
              } else {
                showToast(result.error || "更新失败", "error");
              }
            })
            .catch(function () {
              showToast("网络错误", "error");
            });
        });
      })
      .catch(function () {
        showToast("获取照片信息失败", "error");
      });
  }

  /* ---------- 4c. 编辑注释（全屏查看器内） ---------- */
  function handleViewerEditCaption() {
    var photoId = getCurrentViewerPhotoId();
    if (!photoId) {
      showToast("无法获取照片信息", "error");
      return;
    }
    var editor = document.getElementById("viewerCaptionEditor");
    var input = document.getElementById("viewerCaptionInput");
    if (!editor || !input) return;

    // 先获取当前caption填入输入框
    fetch("/api/photos/" + photoId)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        input.value = data.caption || "";
        editor.style.display = "block";
        input.focus();
      })
      .catch(function () {
        // 获取失败时仍显示编辑器，让用户自行输入
        input.value = "";
        editor.style.display = "block";
        input.focus();
      });
  }

  /* ---------- 4d. 保存注释（全屏查看器内） ---------- */
  window.saveViewerCaption = function () {
    var photoId = getCurrentViewerPhotoId();
    if (!photoId) {
      showToast("无法获取照片信息", "error");
      return;
    }
    var input = document.getElementById("viewerCaptionInput");
    if (!input) return;
    var caption = input.value.trim();

    fetch("/api/photos/" + photoId + "/caption", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ caption: caption })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          showToast("注释已保存");
          closeCaptionEditor();
        } else {
          showToast(data.error || "保存失败", "error");
        }
      })
      .catch(function () {
        showToast("网络错误", "error");
      });
  };

  /* ---------- 4e. 关闭注释编辑器 ---------- */
  window.closeCaptionEditor = function () {
    var editor = document.getElementById("viewerCaptionEditor");
    if (editor) editor.style.display = "none";
  };

  window.viewerPrev = function () {
    if (viewerIndex > 0) slideToIndex(viewerIndex - 1, true);
  };

  window.viewerNext = function () {
    if (viewerIndex < viewerPhotos.length - 1) slideToIndex(viewerIndex + 1, true);
  };

  window.openViewer = function (imgElement) {
    var recordItem = imgElement.closest(".record-item") || imgElement.closest(".cal-detail-item");
    if (!recordItem) return;

    var thumbs = recordItem.querySelectorAll("img[class*='thumb']");
    viewerPhotos = [];
    viewerPhotoIds = {};
    thumbs.forEach(function (thumb) {
      var src = thumb.getAttribute("src") || thumb.dataset.src;
      if (src) {
        viewerPhotos.push(src);
        // 收集照片ID映射
        var pid = thumb.getAttribute("data-photo-id");
        if (pid) viewerPhotoIds[src] = parseInt(pid, 10);
      }
    });

    var clickedSrc = imgElement.getAttribute("src") || imgElement.dataset.src;
    viewerIndex = viewerPhotos.indexOf(clickedSrc);
    if (viewerIndex === -1) viewerIndex = 0;

    showViewer();
  };

  window.openViewerUrl = function (urlOrEl) {
    // 支持传入 img 元素或 URL 字符串
    var imgEl = null;
    var url = urlOrEl;
    if (typeof urlOrEl === 'object' && urlOrEl.tagName === 'IMG') {
      imgEl = urlOrEl;
      url = imgEl.getAttribute('src') || imgEl.src;
    } else {
      // 尝试通过 URL 查找 img 元素（兼容相对路径和绝对路径）
      imgEl = document.querySelector('img[src="' + url + '"]')
             || document.querySelector('img[data-photo-id]');
      // 如果精确匹配失败，遍历所有 img 查找匹配的
      if (!imgEl) {
        var allImgs = document.querySelectorAll('img[data-photo-id]');
        for (var i = 0; i < allImgs.length; i++) {
          if (allImgs[i].src === url || allImgs[i].getAttribute('src') === url) {
            imgEl = allImgs[i];
            break;
          }
        }
      }
    }
    if (imgEl) {
      var photoGroup = imgEl.closest(".photo-group");
      if (photoGroup) {
        var items = photoGroup.querySelectorAll(".photo-item img");
        viewerPhotos = [];
        viewerPhotoIds = {};
        items.forEach(function (item) {
          var src = item.getAttribute("src");
          if (src) {
            viewerPhotos.push(src);
            var pid = item.getAttribute("data-photo-id");
            if (pid) viewerPhotoIds[src] = parseInt(pid, 10);
          }
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
          viewerPhotoIds = {};
          thumbs.forEach(function (thumb) {
            var src = thumb.getAttribute("src");
            if (src) {
              viewerPhotos.push(src);
              var pid = thumb.getAttribute("data-photo-id");
              if (pid) viewerPhotoIds[src] = parseInt(pid, 10);
            }
          });
          viewerIndex = viewerPhotos.indexOf(url);
          if (viewerIndex === -1) viewerIndex = 0;
          showViewer();
          return;
        }
      }
    }

    viewerPhotos = [url];
    viewerPhotoIds = {};
    // 尝试从 img 元素获取 photo ID
    if (imgEl) {
      var pid = imgEl.getAttribute("data-photo-id");
      if (pid) viewerPhotoIds[url] = parseInt(pid, 10);
    }
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

  /* ---------- 6. Tag选择器（全局组件） ---------- */
  // Tag选择器状态变量
  var _tagPickerCallback = null;   // 确认后的回调函数
  var _tagPickerPhotoIndex = null;  // 当前操作的照片索引
  var _allTags = [];                 // 所有标签列表
  var _selectedTagIds = [];          // 当前已选中的标签ID

  /**
   * 加载所有标签（带缓存）
   * @param {function} callback - 加载完成后的回调，参数为标签数组
   */
  window.loadAllTags = function (callback) {
    if (_allTags.length > 0) {
      callback(_allTags);
      return;
    }
    fetch("/api/tags")
      .then(function (res) { return res.json(); })
      .then(function (data) {
        _allTags = data.tags || [];
        callback(_allTags);
      })
      .catch(function () {
        callback([]);
      });
  };

  /**
   * 为指定照片打开Tag选择器
   * @param {number} index - 照片在 selectedFiles 中的索引
   */
  window.openTagPickerForPhoto = function (index) {
    _tagPickerPhotoIndex = index;
    // 从 index.html 的 photoTagIds 数组获取当前照片已选标签
    var currentIds = [];
    if (typeof photoTagIds !== "undefined" && photoTagIds[index]) {
      currentIds = photoTagIds[index].slice();
    }
    openTagPicker(currentIds, function (selectedIds) {
      // 回调：更新 index.html 中的 photoTagIds
      if (typeof photoTagIds !== "undefined") {
        photoTagIds[_tagPickerPhotoIndex] = selectedIds;
      }
      // 更新预览区域的标签显示
      updatePreviewTags(_tagPickerPhotoIndex, selectedIds);
    });
  };

  /**
   * 打开Tag选择弹层
   * @param {array} existingIds - 已选中的标签ID数组
   * @param {function} callback - 确认后的回调，参数为选中的标签ID数组
   */
  window.openTagPicker = function (existingIds, callback) {
    _tagPickerCallback = callback;
    _selectedTagIds = (existingIds || []).slice();

    var overlay = document.getElementById("tagPickerOverlay");
    if (!overlay) return;

    // 清空搜索框
    var searchInput = document.getElementById("tagSearchInput");
    if (searchInput) searchInput.value = "";

    // 加载标签并渲染
    loadAllTags(function (tags) {
      renderTagPickerList(tags, "");
      overlay.style.display = "flex";
      document.body.style.overflow = "hidden";
    });
  };

  /**
   * 关闭Tag选择弹层
   */
  window.closeTagPicker = function () {
    var overlay = document.getElementById("tagPickerOverlay");
    if (overlay) {
      overlay.style.display = "none";
      document.body.style.overflow = "";
    }
    _tagPickerCallback = null;
    _tagPickerPhotoIndex = null;
  };

  /**
   * 搜索/过滤标签列表
   * @param {string} query - 搜索关键词
   */
  window.filterTags = function (query) {
    query = (query || "").trim().toLowerCase();
    var filtered = _allTags.filter(function (tag) {
      return tag.name.toLowerCase().indexOf(query) !== -1;
    });
    renderTagPickerList(filtered, query);

    // 如果没有精确匹配，显示"创建新标签"按钮
    var createDiv = document.getElementById("tagPickerCreate");
    var createBtn = document.getElementById("tagCreateBtn");
    if (createDiv && createBtn) {
      if (query.length > 0 && filtered.every(function (t) { return t.name.toLowerCase() !== query; })) {
        createDiv.style.display = "block";
        createBtn.textContent = '创建 "' + query + '" 标签';
      } else {
        createDiv.style.display = "none";
      }
    }
  };

  /**
   * 从选择器中创建新标签
   */
  window.createTagFromPicker = function () {
    var searchInput = document.getElementById("tagSearchInput");
    var name = (searchInput ? searchInput.value.trim() : "");
    if (!name) return;

    fetch("/api/tags", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name })
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.success && data.tag) {
          // 添加到本地缓存
          _allTags.push(data.tag);
          // 自动选中新创建的标签
          if (_selectedTagIds.indexOf(data.tag.id) === -1) {
            _selectedTagIds.push(data.tag.id);
          }
          // 清空搜索并重新渲染
          if (searchInput) searchInput.value = "";
          var createDiv = document.getElementById("tagPickerCreate");
          if (createDiv) createDiv.style.display = "none";
          renderTagPickerList(_allTags, "");
          showToast("标签已创建");
        } else {
          showToast(data.error || data.message || "创建失败");
        }
      })
      .catch(function () {
        showToast("网络错误");
      });
  };

  /**
   * 确认Tag选择
   */
  window.confirmTagPicker = function () {
    if (typeof _tagPickerCallback === "function") {
      _tagPickerCallback(_selectedTagIds.slice());
    }
    closeTagPicker();
  };

  /**
   * 渲染Tag选择器列表
   * @param {array} tags - 要渲染的标签数组
   * @param {string} query - 当前搜索词（用于高亮）
   */
  function renderTagPickerList(tags, query) {
    var listEl = document.getElementById("tagPickerList");
    if (!listEl) return;
    listEl.innerHTML = "";

    if (tags.length === 0) {
      listEl.innerHTML = '<div style="text-align:center;padding:1.5rem;color:var(--pencil);font-size:0.85rem;">无匹配标签</div>';
      return;
    }

    tags.forEach(function (tag) {
      var item = document.createElement("div");
      item.className = "tag-picker-item" + (_selectedTagIds.indexOf(tag.id) !== -1 ? " selected" : "");
      item.setAttribute("data-id", tag.id);

      // 标签名称
      var nameSpan = document.createElement("span");
      nameSpan.className = "tag-picker-item-name";
      nameSpan.textContent = tag.name;
      item.appendChild(nameSpan);

      // 计数（如果有）
      if (tag.count !== undefined) {
        var countSpan = document.createElement("span");
        countSpan.className = "tag-picker-item-count";
        countSpan.textContent = tag.count;
        item.appendChild(countSpan);
      }

      // 选中状态指示
      var checkSpan = document.createElement("span");
      checkSpan.className = "tag-picker-item-check";
      checkSpan.textContent = _selectedTagIds.indexOf(tag.id) !== -1 ? "\u2713" : "";
      item.appendChild(checkSpan);

      // 点击切换选中
      item.addEventListener("click", function () {
        var idx = _selectedTagIds.indexOf(tag.id);
        if (idx === -1) {
          _selectedTagIds.push(tag.id);
        } else {
          _selectedTagIds.splice(idx, 1);
        }
        renderTagPickerList(tags, query);
      });

      listEl.appendChild(item);
    });
  }

  /**
   * 更新照片预览区域的标签显示
   * @param {number} photoIndex - 照片索引
   * @param {array} tagIds - 选中的标签ID数组
   */
  function updatePreviewTags(photoIndex, tagIds) {
    // 查找对应的预览项
    var previewItems = document.querySelectorAll(".preview-item");
    var targetItem = null;
    previewItems.forEach(function (item) {
      if (parseInt(item.getAttribute("data-index"), 10) === photoIndex) {
        targetItem = item;
      }
    });
    if (!targetItem) return;

    var tagsDiv = targetItem.querySelector(".preview-tags");
    if (!tagsDiv) return;

    // 清空现有标签（保留添加按钮）
    var addBtn = tagsDiv.querySelector(".preview-add-tag");
    tagsDiv.innerHTML = "";
    if (addBtn) {
      addBtn.setAttribute("data-index", photoIndex);
      tagsDiv.appendChild(addBtn);
    } else {
      var newAddBtn = document.createElement("button");
      newAddBtn.type = "button";
      newAddBtn.className = "preview-add-tag";
      newAddBtn.textContent = "+标签";
      newAddBtn.setAttribute("data-index", photoIndex);
      newAddBtn.addEventListener("click", function () {
        var ti = parseInt(this.getAttribute("data-index"), 10);
        openTagPickerForPhoto(ti);
      });
      tagsDiv.appendChild(newAddBtn);
    }

    // 渲染选中的标签
    tagIds.forEach(function (tagId) {
      var tag = _allTags.find(function (t) { return t.id === tagId; });
      if (!tag) return;

      var badge = document.createElement("span");
      badge.className = "preview-tag";
      badge.textContent = tag.name;
      badge.setAttribute("data-tag-id", tag.id);

      // 点击标签可取消选择
      badge.addEventListener("click", function () {
        var idx = tagIds.indexOf(tagId);
        if (idx > -1) tagIds.splice(idx, 1);
        updatePreviewTags(photoIndex, tagIds);
        // 同步到 photoTagIds
        if (typeof photoTagIds !== "undefined") {
          photoTagIds[photoIndex] = tagIds;
        }
      });

      tagsDiv.appendChild(badge);
    });
  }

  /**
   * 渲染一个标签小徽章（工具函数，可在其他地方复用）
   * @param {string} tagName - 标签名称
   * @returns {HTMLElement}
   */
  window.renderTagBadge = function (tagName) {
    var badge = document.createElement("span");
    badge.className = "preview-tag";
    badge.textContent = tagName;
    return badge;
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

    // Tag选择器遮罩点击关闭
    var tagPickerOverlay = document.getElementById("tagPickerOverlay");
    if (tagPickerOverlay) {
      tagPickerOverlay.addEventListener("click", function (e) {
        if (e.target === tagPickerOverlay) {
          closeTagPicker();
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
    // 编辑标签按钮
    var editTagsBtn = document.getElementById("viewerEditTags");
    if (editTagsBtn) {
      editTagsBtn.addEventListener("click", handleViewerEditTags);
    }
    // 编辑注释按钮
    var editCaptionBtn = document.getElementById("viewerEditCaption");
    if (editCaptionBtn) {
      editCaptionBtn.addEventListener("click", handleViewerEditCaption);
    }
  })();

  /* ---------- I5. 触摸滑动（轨道跟手拖拽） ---------- */
  (function initViewerTouch() {
    var overlay = document.getElementById("viewerOverlay");
    var body = getBody();
    if (!overlay || !body) return;

    var startX = 0;
    var startY = 0;
    var dragOffset = 0;
    var isDragging = false;
    var isHorizontal = null;

    overlay.addEventListener("touchstart", function (e) {
      startX = e.changedTouches[0].clientX;
      startY = e.changedTouches[0].clientY;
      dragOffset = 0;
      isDragging = true;
      isHorizontal = null;
    }, { passive: true });

    overlay.addEventListener("touchmove", function (e) {
      if (!isDragging) return;

      var dx = e.changedTouches[0].clientX - startX;
      var dy = e.changedTouches[0].clientY - startY;

      if (isHorizontal === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
        isHorizontal = Math.abs(dx) > Math.abs(dy);
      }
      if (!isHorizontal) return;

      // 基准位置 + 拖拽偏移
      var baseOffset = -viewerIndex * body.clientWidth;
      dragOffset = dx;

      // 边缘阻力
      if ((viewerIndex === 0 && dx > 0) || (viewerIndex === viewerPhotos.length - 1 && dx < 0)) {
        dragOffset = dx * 0.3;
      }

      setTrackPosition(baseOffset + dragOffset, false);
    }, { passive: true });

    overlay.addEventListener("touchend", function () {
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
    }, { passive: true });
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
        // Tag选择器 Escape 关闭
        var tagPickerOverlay = document.getElementById("tagPickerOverlay");
        if (tagPickerOverlay && tagPickerOverlay.style.display !== "none") {
          closeTagPicker();
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

  // 辅助：HTML转义
  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /* ---------- I7. 设置关闭按钮 ---------- */
  (function initSettingsClose() {
    var closeBtn = document.getElementById("settingsClose");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        closeSettings();
      });
    }
  })();

  /* ---------- I8. 全局排序设置 ---------- */
  // 从 localStorage 读取排序偏好，默认从新到旧
  var _sortOrder = localStorage.getItem("photo_sort_order") || "desc";

  window.getSortOrder = function () {
    return _sortOrder;
  };

  window.setSortOrder = function (order) {
    _sortOrder = order;
    localStorage.setItem("photo_sort_order", order);
    // 更新设置面板按钮样式
    document.querySelectorAll(".sort-option").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-order") === order);
    });
    // 触发自定义事件，通知各页面重新渲染
    window.dispatchEvent(new CustomEvent("sortOrderChanged", { detail: order }));
  };

  // 初始化设置面板按钮状态
  (function initSortButtons() {
    document.querySelectorAll(".sort-option").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-order") === _sortOrder);
    });
  })();

})();
