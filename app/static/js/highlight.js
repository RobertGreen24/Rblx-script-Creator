/* A small Luau tokenizer for syntax highlighting. Ships with zero dependencies.
   Order matters in the pattern below: comments and strings win over keywords. */
window.RFHighlight = (function () {
  "use strict";

  var KEYWORDS =
    "local|function|end|if|then|else|elseif|for|while|do|repeat|until|return|break|continue|" +
    "and|or|not|in|nil|true|false|export|type";

  var GLOBALS =
    "self|game|workspace|script|Instance|Enum|Vector3|Vector2|Vector2int16|Vector3int16|CFrame|Color3|" +
    "ColorSequence|ColorSequenceKeypoint|NumberRange|NumberSequence|NumberSequenceKeypoint|UDim|UDim2|" +
    "Rect|Region3|TweenInfo|BrickColor|Random|Faces|Axes|PhysicalProperties|Ray|Flee|Font|TextChatMessage|" +
    "task|math|string|table|os|coroutine|utf8|debug|bit32|buffer|vector|shared|" +
    "require|typeof|print|warn|error|assert|pcall|xpcall|tostring|tonumber|pairs|ipairs|next|select|unpack|" +
    "setmetatable|getmetatable|rawget|rawset|rawequal|rawlen|newproxy|collectgarbage|tick|time|wait|spawn|delay|" +
    "DateTime|OverlapParams|RaycastParams|TweenService";

  var PATTERN = new RegExp(
    [
      "(--\\[\\[[\\s\\S]*?\\]\\])", // 1 long comment
      "(--[^\\n]*)", // 2 line comment
      '("(?:\\\\.|[^"\\\\\\n])*")', // 3 double-quoted string
      "('(?:\\\\.|[^'\\\\\\n])*')", // 4 single-quoted string
      "(\\[\\[[\\s\\S]*?\\]\\])", // 5 long string
      "(\\b\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?\\b|\\.\\d+)", // 6 number
      "(\\b(?:" + KEYWORDS + ")\\b)", // 7 keyword
      "(\\b(?:" + GLOBALS + ")\\b)", // 8 builtin
      "(\\b[A-Za-z_]\\w*(?=\\s*\\())", // 9 function call
      "(\\b[A-Za-z_]\\w*\\b)" // 10 identifier
    ].join("|"),
    "g"
  );

  var CLASSES = {
    1: "tok-com",
    2: "tok-com",
    3: "tok-str",
    4: "tok-str",
    5: "tok-str",
    6: "tok-num",
    7: "tok-kw",
    8: "tok-glb",
    9: "tok-fn",
    10: "tok-id"
  };

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function highlight(code) {
    var output = "";
    var lastIndex = 0;
    var match;

    PATTERN.lastIndex = 0;
    while ((match = PATTERN.exec(code)) !== null) {
      if (match.index > lastIndex) {
        output += escapeHtml(code.slice(lastIndex, match.index));
      }

      var group = 1;
      for (var index = 1; index <= 10; index += 1) {
        if (match[index] !== undefined) {
          group = index;
          break;
        }
      }
      output += '<span class="' + CLASSES[group] + '">' + escapeHtml(match[group]) + "</span>";
      lastIndex = match.index + match[group].length;
    }

    output += escapeHtml(code.slice(lastIndex));
    return output;
  }

  return { highlight: highlight };
})();
