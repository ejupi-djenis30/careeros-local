const HISTORY_LIMIT = 50;

const clone = (value) => value == null ? value : structuredClone(value);

export function createCanvasState(document) {
    return { past: [], present: clone(document), future: [] };
}

function commit(state, present) {
    if (present === state.present) return state;
    return {
        past: [...state.past, state.present].slice(-HISTORY_LIMIT),
        present,
        future: [],
    };
}

function updateSection(document, sectionId, updater) {
    return {
        ...document,
        sections: document.sections.map((section) => section.id === sectionId ? updater(section) : section),
    };
}

function move(items, from, to) {
    if (from < 0 || to < 0 || from >= items.length || to >= items.length || from === to) return items;
    const next = [...items];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    return next;
}

function manualClaim(blockId) {
    return {
        id: blockId,
        kind: "fact",
        fact_ids: [],
        visible: true,
        content: { title: "", subtitle: "", date_range: "", description: "", bullets: [] },
        manual_fields: ["title", "subtitle", "description", "bullets"],
    };
}

function reduceDocument(document, action) {
    if (action.type === "SET_STYLE") return { ...document, style: { ...document.style, [action.field]: action.value } };
    if (action.type === "ADD_MANUAL_CLAIM") {
        const blockCount = document.sections.reduce((total, section) => total + section.blocks.length, 0);
        if (blockCount >= 300) return document;
        const existing = document.sections.find((section) => section.kind === "achievement");
        if (existing) {
            return updateSection(document, existing.id, (section) => ({ ...section, blocks: [...section.blocks, manualClaim(action.blockId)] }));
        }
        return {
            ...document,
            sections: [...document.sections, { id: "achievement", kind: "achievement", title: "RISULTATI", visible: true, page_break_before: false, blocks: [manualClaim(action.blockId)] }],
        };
    }
    if (action.type === "REMOVE_BLOCK") {
        const updated = updateSection(document, action.sectionId, (section) => ({ ...section, blocks: section.blocks.filter((block) => block.id !== action.blockId) }));
        return { ...updated, sections: updated.sections.filter((section) => section.kind !== "achievement" || section.blocks.length > 0) };
    }
    if (action.type === "MOVE_SECTION") {
        const from = document.sections.findIndex((section) => section.id === action.sectionId);
        const to = action.toIndex ?? from + action.direction;
        const sections = move(document.sections, from, to);
        return sections === document.sections ? document : { ...document, sections };
    }
    if (["SET_SECTION_VISIBLE", "SET_SECTION_TITLE", "SET_PAGE_BREAK", "MOVE_BLOCK", "UPDATE_BLOCK", "SET_BLOCK_VISIBLE"].includes(action.type)) {
        return updateSection(document, action.sectionId, (section) => {
            if (action.type === "SET_SECTION_VISIBLE") return { ...section, visible: action.visible };
            if (action.type === "SET_SECTION_TITLE") return { ...section, title: action.title };
            if (action.type === "SET_PAGE_BREAK") return { ...section, page_break_before: action.enabled };
            if (action.type === "MOVE_BLOCK") {
                const from = section.blocks.findIndex((block) => block.id === action.blockId);
                const to = action.toIndex ?? from + action.direction;
                const blocks = move(section.blocks, from, to);
                return blocks === section.blocks ? section : { ...section, blocks };
            }
            return {
                ...section,
                blocks: section.blocks.map((block) => {
                    if (block.id !== action.blockId) return block;
                    if (action.type === "SET_BLOCK_VISIBLE") return { ...block, visible: action.visible };
                    const manual = new Set(block.manual_fields || []);
                    manual.add(action.field);
                    return {
                        ...block,
                        content: { ...block.content, [action.field]: action.value },
                        manual_fields: [...manual],
                    };
                }),
            };
        });
    }
    return document;
}

export function canvasReducer(state, action) {
    if (action.type === "LOAD") return createCanvasState(action.document);
    if (action.type === "UNDO") {
        if (!state.past.length) return state;
        return {
            past: state.past.slice(0, -1),
            present: state.past.at(-1),
            future: [state.present, ...state.future].slice(0, HISTORY_LIMIT),
        };
    }
    if (action.type === "REDO") {
        if (!state.future.length) return state;
        return {
            past: [...state.past, state.present].slice(-HISTORY_LIMIT),
            present: state.future[0],
            future: state.future.slice(1),
        };
    }
    return commit(state, reduceDocument(state.present, action));
}
