import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// Nodes from ComfyUI-VoiceLibrarySaver that should (a) show a status line and
// (b) refresh every dropdown in the graph after they run.
const VOICE_NODES = [
    "VoiceLibrarySaver",
    "VoiceLibraryDelete",
    "VoiceLibraryRestore",
    "VoiceLibraryPurge",
    "VoiceLibraryRename",
    "VoiceLibraryPreview",
    "VoiceLibraryList",
    "VoiceLibraryDuplicate",
    "VoiceLibraryBackup",
];

function setStatus(node, text) {
    // Create a read-only multiline widget the first time, then reuse it.
    if (!node._statusWidget) {
        const w = ComfyWidgets["STRING"](
            node,
            "status",
            ["STRING", { multiline: true }],
            app
        ).widget;
        w.inputEl.readOnly = true;
        w.inputEl.style.opacity = "0.85";
        w.inputEl.style.fontWeight = "bold";
        node._statusWidget = w;
    }
    node._statusWidget.value = text;
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "VoiceLibrary.StatusAndRefresh",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!VOICE_NODES.includes(nodeData.name)) return;

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);

            // 1) Show the status text right on the node.
            const lines = message?.text;
            if (lines && lines.length) {
                setStatus(this, lines.join("\n"));
            }

            // 2) Refresh every dropdown in the graph so the voice lists are
            //    up to date (same thing the toolbar refresh / "R" key does).
            if (app.refreshComboInNodes) {
                Promise.resolve(app.refreshComboInNodes()).catch(() => {});
            }
        };
    },
});
