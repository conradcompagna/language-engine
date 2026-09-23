import { dependencyPopupState } from './dependency-popup.state.mjs';
import { presentationState } from './presentation.state.mjs';
export function buildUdPopupHtml(segIdx) {
  // UD popup disabled - tags moved to dictionary headline
  return '';
}

// NEW: Build tag badges for dictionary headline (moved from UD popup)
// This function is now deprecated as POS tags are rendered directly from the entry.
export function buildUdTagsForHeadline(segIdx) {
  return '';
}
// ===================== END UD VISUALIZATION =====================

// Display toggle state - load from localStorage or use defaults
export function ensureLmWeightsInitialized() {
  if (
    !dependencyPopupState.displaySettings.lmWeights ||
    typeof dependencyPopupState.displaySettings.lmWeights !== 'object'
  ) {
    dependencyPopupState.displaySettings.lmWeights = {};
  }
  Object.keys(dependencyPopupState.LM_WEIGHT_DEFAULTS).forEach(function (key) {
    var val = dependencyPopupState.displaySettings.lmWeights[key];
    if (typeof val === 'string') {
      var parsed = parseFloat(val);
      if (isFinite(parsed)) {
        dependencyPopupState.displaySettings.lmWeights[key] = parsed;
        return;
      }
    }
    if (typeof val !== 'number' || !isFinite(val)) {
      dependencyPopupState.displaySettings.lmWeights[key] = dependencyPopupState.LM_WEIGHT_DEFAULTS[key];
    }
  });
}

// ===================== CHUNK HIGHLIGHTING =====================
// POS-based colors for chunk highlighting - matches SPACY_UPOS_COLORS
export // Build chunk structure from UD overlay
// Returns: {
//   chunks: [{headSeg, members: Set, depth, pos}],
//   tokenToChunks: Map<seg, [{chunk, depth}]>,
//   canonicalChunk: Map<seg, chunk>,  // The finest-grained chunk for each token
//   children: Map<seg, [seg]>,         // Parent->children adjacency
//   tokenMap: Map<seg, token>
// }
function computeChunks(udOverlay, maxDepth, useLinearClauseSplit, branchDepthMin, clauseDepthDrop) {
  if (!udOverlay || !udOverlay.ok || maxDepth <= 0) {
    return {
      chunks: [],
      tokenToChunks: new Map(),
      canonicalChunk: new Map(),
      children: new Map(),
      tokenMap: new Map()
    };
  }
  var tokens = udOverlay.tokens || [];
  var roots = udOverlay.roots || [];

  // Build token map and children adjacency
  var tokenMap = new Map();
  var children = new Map(); // parent seg -> [child segs]
  var parentOf = new Map(); // child seg -> parent seg

  tokens.forEach(function (t) {
    tokenMap.set(t.i, t);
    if (!children.has(t.i)) children.set(t.i, []);
  });
  tokens.forEach(function (t) {
    if (Array.isArray(t.heads)) {
      // MWT multi-head: register as child of all heads, parentOf uses first
      for (var mhi = 0; mhi < t.heads.length; mhi++) {
        var mhIdx = t.heads[mhi];
        if (mhIdx !== undefined && mhIdx !== t.i && tokenMap.has(mhIdx)) {
          if (!children.has(mhIdx)) children.set(mhIdx, []);
          children.get(mhIdx).push(t.i);
          if (!parentOf.has(t.i)) parentOf.set(t.i, mhIdx);
        }
      }
    } else if (t.head !== undefined && t.head !== t.i && tokenMap.has(t.head)) {
      if (!children.has(t.head)) children.set(t.head, []);
      children.get(t.head).push(t.i);
      parentOf.set(t.i, t.head);
    }
  });

  // Compute depth from roots using BFS
  var depthOf = new Map();
  var queue = [];
  roots.forEach(function (r) {
    depthOf.set(r, 0);
    queue.push(r);
  });
  // Also add any tokens not reachable from roots (treat as depth 0)
  tokens.forEach(function (t) {
    if (!depthOf.has(t.i) && !parentOf.has(t.i)) {
      depthOf.set(t.i, 0);
      queue.push(t.i);
    }
  });
  while (queue.length) {
    var cur = queue.shift();
    var curDepth = depthOf.get(cur);
    var kids = children.get(cur) || [];
    kids.forEach(function (kid) {
      if (!depthOf.has(kid)) {
        depthOf.set(kid, curDepth + 1);
        queue.push(kid);
      }
    });
  }

  // Optional clause splitting: linear left-to-right (strict ancestor chain).
  var clauseGroup = null;
  if (useLinearClauseSplit) {
    clauseGroup = new Map();

    // Get all heads (tokens with children)
    var heads = [];
    tokens.forEach(function (t) {
      var kids = children.get(t.i) || [];
      if (kids.length > 0) {
        heads.push(t.i);
      }
    });

    // Sort by position (segment index)
    heads.sort(function (a, b) {
      return a - b;
    });

    // Get ancestor chain for a token (walking up the actual dependency tree)
    function getAncestorChain(seg) {
      var chain = [];
      var cur = seg;
      var visited = new Set();
      while (cur !== undefined && !visited.has(cur)) {
        visited.add(cur);
        chain.push(cur);
        cur = parentOf.get(cur);
      }
      return chain; // [seg, parent, grandparent, ..., root]
    }
    function branchDepth(seg, maxDepth) {
      var depth = 0;
      var stack = [
        {
          seg: seg,
          d: 0
        }
      ];
      var seen = new Set();
      while (stack.length) {
        var item = stack.pop();
        var cur = item.seg;
        var d = item.d;
        if (seen.has(cur)) continue;
        seen.add(cur);
        if (d > depth) depth = d;
        if (d >= maxDepth) continue;
        var kids = children.get(cur) || [];
        kids.forEach(function (kid) {
          if ((children.get(kid) || []).length > 0) {
            stack.push({
              seg: kid,
              d: d + 1
            });
          }
        });
      }
      return depth;
    }
    var minDepth = Math.max(1, Math.min(5, branchDepthMin || 1));
    var branchHeads = heads.filter(function (seg) {
      return branchDepth(seg, minDepth) >= minDepth;
    });
    if (heads.length === 0 || branchHeads.length === 0) {
      // No heads - all tokens in one group
      tokens.forEach(function (t) {
        clauseGroup.set(t.i, 1);
      });
    } else {
      // Linear left-to-right clause grouping: heads must stay on one direct path to root
      function isStrictBranch(seg1, seg2) {
        var chain1 = getAncestorChain(seg1);
        var chain2 = getAncestorChain(seg2);
        var set1 = new Set(chain1);
        var set2 = new Set(chain2);
        return set1.has(seg2) || set2.has(seg1);
      }
      // Use only branch heads to define clauses.
      var groupId = 1;
      var prevHead = branchHeads[0];
      clauseGroup.set(prevHead, groupId);
      for (var i = 1; i < branchHeads.length; i++) {
        var curHead = branchHeads[i];
        if (!isStrictBranch(curHead, prevHead)) {
          groupId++;
        }
        clauseGroup.set(curHead, groupId);
        prevHead = curHead;
      }

      // Assign groups to all heads so the postpass can evaluate full head sequences.
      heads.forEach(function (h) {
        if (clauseGroup.has(h)) return;
        var cur = h;
        var seen = new Set();
        while (cur !== undefined && !seen.has(cur)) {
          seen.add(cur);
          if (clauseGroup.has(cur)) {
            clauseGroup.set(h, clauseGroup.get(cur));
            break;
          }
          cur = parentOf.get(cur);
        }
        if (!clauseGroup.has(h)) clauseGroup.set(h, 0);
      });

      // Include singleton leaf tokens in the postpass.
      var standaloneLeaves = [];
      tokens.forEach(function (t) {
        var kids = children.get(t.i) || [];
        if (kids.length > 0) return;
        standaloneLeaves.push(t.i);
        if (clauseGroup.has(t.i)) return;
        var cur = t.i;
        var seen = new Set();
        while (cur !== undefined && !seen.has(cur)) {
          seen.add(cur);
          if (clauseGroup.has(cur)) {
            clauseGroup.set(t.i, clauseGroup.get(cur));
            break;
          }
          cur = parentOf.get(cur);
        }
        if (!clauseGroup.has(t.i)) clauseGroup.set(t.i, 0);
      });

      // Postpass: split on large depth drops within each clause head sequence.
      var headsByGroup = new Map();
      var postpassNodes = heads.concat(standaloneLeaves);
      postpassNodes.forEach(function (h) {
        var grp = clauseGroup.get(h);
        if (!grp) return;
        if (!headsByGroup.has(grp)) headsByGroup.set(grp, []);
        headsByGroup.get(grp).push(h);
      });
      var nextGroupId = groupId + 1;
      var depthDropMin = Math.max(0, Math.min(10, clauseDepthDrop !== undefined ? clauseDepthDrop : 3));
      headsByGroup.forEach(function (list) {
        list.sort(function (a, b) {
          return a - b;
        });
        var currentGroup = clauseGroup.get(list[0]);
        var prevDepth = depthOf.get(list[0]) || 0;
        clauseGroup.set(list[0], currentGroup);
        for (var hi = 1; hi < list.length; hi++) {
          var curHead = list[hi];
          var curDepth = depthOf.get(curHead) || 0;
          if (curDepth - prevDepth >= depthDropMin) {
            currentGroup = nextGroupId++;
          }
          clauseGroup.set(curHead, currentGroup);
          prevDepth = curDepth;
        }
      });
    }

    // Propagate groups to non-head tokens (each gets its nearest head ancestor's group)

    tokens.forEach(function (t) {
      if (clauseGroup.has(t.i)) return;

      // Walk up to find nearest head ancestor with a group
      var cur = t.i;
      var seen = new Set();
      while (cur !== undefined && !seen.has(cur)) {
        seen.add(cur);
        if (clauseGroup.has(cur)) {
          clauseGroup.set(t.i, clauseGroup.get(cur));
          break;
        }
        cur = parentOf.get(cur);
      }

      // If no ancestor found, assign to group 0
      if (!clauseGroup.has(t.i)) clauseGroup.set(t.i, 0);
    });
    function isHeadSeg(seg) {
      var kids = children.get(seg) || [];
      return kids.length > 0;
    }
    var headSegs = [];
    var headSet = new Set();
    tokens.forEach(function (t) {
      if (isHeadSeg(t.i)) {
        headSegs.push(t.i);
        headSet.add(t.i);
      }
    });
    if (headSegs.length === 0) {
      tokens.forEach(function (t) {
        headSegs.push(t.i);
        headSet.add(t.i);
      });
    }
    var splitMultiHeadOutClauseGroups = function () {
      var groupMembers = new Map();
      var groupMembersAll = new Map();
      var maxGroupId = 0;
      tokens.forEach(function (t) {
        var seg = t.i;
        var grpVal = clauseGroup.get(seg);
        if (grpVal === undefined || grpVal === 0) return;
        if (!groupMembersAll.has(grpVal)) groupMembersAll.set(grpVal, []);
        groupMembersAll.get(grpVal).push(seg);
        if (headSet.has(seg)) {
          if (!groupMembers.has(grpVal)) groupMembers.set(grpVal, []);
          groupMembers.get(grpVal).push(seg);
        }
        if (grpVal > maxGroupId) maxGroupId = grpVal;
      });
      var nextSplitGroupId = maxGroupId + 1;
      groupMembersAll.forEach(function (allMembers, grpVal) {
        var members = groupMembers.get(grpVal) || [];
        var memberSetAll = new Set(allMembers);

        // Find all members (not just heads) whose parent is outside the group
        var topLevel = [];
        var topParent = null;
        var allSameParent = true;
        allMembers.forEach(function (seg) {
          var parent = parentOf.get(seg);
          if (parent === undefined || !memberSetAll.has(parent)) {
            topLevel.push(seg);
            if (topParent === null) topParent = parent;
            else if (topParent !== parent) allSameParent = false;
          }
        });

        // Key guard: if multiple members point to the same external parent
        // (meaning the apex is outside the clause), split them into separate clauses
        var splitAnchors;
        var assignMembers;
        if (
          topLevel.length > 1 &&
          allSameParent &&
          (topParent === undefined || !memberSetAll.has(topParent))
        ) {
          // Multiple members converge to the same external parent - split each into its own clause
          splitAnchors = topLevel;
          assignMembers = allMembers;
        } else {
          // Fall back to original head-out logic
          var headOuts = [];
          members.forEach(function (seg) {
            var parent = parentOf.get(seg);
            if (parent === undefined || !memberSetAll.has(parent)) {
              headOuts.push(seg);
            }
          });
          splitAnchors = headOuts;
          assignMembers = members;
        }
        if (splitAnchors.length <= 1) return;
        var headToGroup = new Map();
        headToGroup.set(splitAnchors[0], grpVal);
        for (var ho = 1; ho < splitAnchors.length; ho++) {
          headToGroup.set(splitAnchors[ho], nextSplitGroupId++);
        }
        assignMembers.forEach(function (seg) {
          var cur = seg;
          var seen = new Set();
          while (cur !== undefined && !seen.has(cur)) {
            seen.add(cur);
            if (headToGroup.has(cur)) {
              clauseGroup.set(seg, headToGroup.get(cur));
              return;
            }
            var p = parentOf.get(cur);
            if (p === undefined || !memberSetAll.has(p)) {
              if (!headToGroup.has(cur)) {
                headToGroup.set(cur, nextSplitGroupId++);
              }
              clauseGroup.set(seg, headToGroup.get(cur));
              return;
            }
            cur = p;
          }
          clauseGroup.set(seg, grpVal);
        });
      });
    };
    var propagateGroupsToNonHeads = function () {
      tokens.forEach(function (t) {
        if (headSet.has(t.i)) return;
        var cur = t.i;
        var seen = new Set();
        while (cur !== undefined && !seen.has(cur)) {
          seen.add(cur);
          if (headSet.has(cur) && clauseGroup.has(cur)) {
            clauseGroup.set(t.i, clauseGroup.get(cur));
            return;
          }
          cur = parentOf.get(cur);
        }
        if (!clauseGroup.has(t.i)) clauseGroup.set(t.i, 0);
      });
    };

    // Postpass: split clause groups that have multiple heads pointing outside the group.
    splitMultiHeadOutClauseGroups();

    // Sync non-head tokens to their nearest head before contiguity.
    propagateGroupsToNonHeads();

    // Postpass guard: enforce contiguous clause spans by token order.
    var orderedSegs = tokens.map(function (t) {
      return t.i;
    });
    orderedSegs.sort(function (a, b) {
      return a - b;
    });
    var remapGroupId = 0;
    var prevGroup = null;
    orderedSegs.forEach(function (seg) {
      var grp = clauseGroup.get(seg);
      if (grp === 0) return;
      if (grp !== prevGroup) {
        remapGroupId++;
        prevGroup = grp;
      }
      clauseGroup.set(seg, remapGroupId);
    });

    // Final postpass: split orphaned clauses whose head is outside the group (after contiguity split them off)
    splitMultiHeadOutClauseGroups();
  }

  // Get root phrase: root + only CONTIGUOUS leaf children
  // Children with children form their own clauses and are NOT part of root phrase
  // Non-contiguous leaf children become their own singleton chunks
  function getRootPhrase(rootSeg) {
    var kids = children.get(rootSeg) || [];

    // Find all leaf children (no grandchildren)
    var leafKids = [];
    kids.forEach(function (k) {
      var grandkids = children.get(k) || [];
      if (grandkids.length === 0) {
        leafKids.push(k);
      }
    });
    if (leafKids.length === 0) {
      return new Set([rootSeg]); // Just the root itself
    }

    // Build set of candidates (root + leaf kids)
    var candidateSet = new Set(leafKids);
    candidateSet.add(rootSeg);

    // Start from root and expand to adjacent candidates only (contiguous)
    var members = new Set();
    var toCheck = [rootSeg];
    var checked = new Set();
    while (toCheck.length > 0) {
      var current = toCheck.pop();
      if (checked.has(current)) continue;
      checked.add(current);

      // Only add if it's a valid candidate
      if (candidateSet.has(current)) {
        members.add(current);

        // Check adjacent token indices
        if (candidateSet.has(current - 1) && !checked.has(current - 1)) {
          toCheck.push(current - 1);
        }
        if (candidateSet.has(current + 1) && !checked.has(current + 1)) {
          toCheck.push(current + 1);
        }
      }
    }
    return members;
  }

  // Get subtree members for a token, but only contiguous leaf children
  // Returns { members: Set, nonContiguousLeaves: Array }
  function getSubtreeContiguous(seg) {
    var members = new Set([seg]);
    var nonContiguousLeaves = [];

    // First pass: recursively add all non-leaf children and their subtrees
    var stack = [seg];
    while (stack.length) {
      var cur = stack.pop();
      var kids = children.get(cur) || [];
      kids.forEach(function (k) {
        var grandkids = children.get(k) || [];
        if (grandkids.length > 0) {
          // Non-leaf child: add it and continue recursion
          if (!members.has(k)) {
            members.add(k);
            stack.push(k);
          }
        }
        // Leaf children handled separately for contiguity check
      });
    }

    // Second pass: for each token in members, keep only leaf kids contiguous to that parent
    var membersArray = Array.from(members);
    membersArray.forEach(function (m) {
      var kids = children.get(m) || [];
      var leafKids = [];
      kids.forEach(function (k) {
        var grandkids = children.get(k) || [];
        if (grandkids.length === 0) {
          leafKids.push(k);
        }
      });
      if (leafKids.length === 0) return;
      var candidate = new Set(leafKids);
      candidate.add(m);
      var local = new Set();
      var stack2 = [m];
      while (stack2.length) {
        var cur = stack2.pop();
        if (local.has(cur)) continue;
        if (!candidate.has(cur)) continue;
        local.add(cur);
        if (candidate.has(cur - 1) && !local.has(cur - 1)) stack2.push(cur - 1);
        if (candidate.has(cur + 1) && !local.has(cur + 1)) stack2.push(cur + 1);
      }
      leafKids.forEach(function (leaf) {
        if (local.has(leaf)) {
          members.add(leaf);
        } else {
          nonContiguousLeaves.push(leaf);
        }
      });
    });
    return {
      members: members,
      nonContiguousLeaves: nonContiguousLeaves
    };
  }

  // Simple getSubtree for backward compatibility (full subtree, no contiguity check)
  function getSubtree(seg) {
    var members = new Set([seg]);
    var stack = [seg];
    while (stack.length) {
      var cur = stack.pop();
      var kids = children.get(cur) || [];
      kids.forEach(function (k) {
        if (!members.has(k)) {
          members.add(k);
          stack.push(k);
        }
      });
    }
    return members;
  }

  // Check if token has children (i.e., is a chunk head candidate)
  function hasChildren(seg) {
    var kids = children.get(seg) || [];
    return kids.length > 0;
  }

  // Build chunks by depth level
  var allChunks = [];
  var tokenToChunks = new Map(); // seg -> [{chunk, depth}]
  var canonicalChunk = new Map(); // seg -> chunk (finest-grained)

  // Initialize tokenToChunks
  tokens.forEach(function (t) {
    tokenToChunks.set(t.i, []);
  });

  // Process depth 0 (roots) - roots with children form phrase chunks
  // Root's chunk is itself + CONTIGUOUS leaf children only
  // Non-contiguous leaf children become explicit singleton chunks
  tokens.forEach(function (t) {
    if (depthOf.get(t.i) === 0 && hasChildren(t.i)) {
      var members = getRootPhrase(t.i); // Root + contiguous leaf children only
      var rootExtras = [];
      var chunk = {
        headSeg: t.i,
        members: members,
        depth: 0,
        pos: 'ROOT',
        // Use special ROOT color for root phrase
        isRootPhrase: true
      };
      allChunks.push(chunk);

      // Register this chunk for members only
      members.forEach(function (m) {
        var list = tokenToChunks.get(m);
        if (list)
          list.push({
            chunk: chunk,
            depth: 0
          });
      });

      // Create explicit singleton chunks for non-contiguous leaf children of root
      var kids = children.get(t.i) || [];
      kids.forEach(function (kid) {
        var grandkids = children.get(kid) || [];
        // Only leaf children (no grandkids) that aren't in root phrase
        if (grandkids.length === 0 && !members.has(kid)) {
          rootExtras.push(kid);
          var singletonChunk = {
            headSeg: kid,
            members: new Set([kid]),
            depth: 0,
            // Same depth level as root phrase
            pos:
              tokens.find(function (tok) {
                return tok.i === kid;
              })?.upos || 'DEFAULT',
            isSingleton: true,
            isNonContiguousLeaf: true
          };
          allChunks.push(singletonChunk);
          var kidList = tokenToChunks.get(kid);
          if (kidList)
            kidList.push({
              chunk: singletonChunk,
              depth: 0
            });
        }
      });
      if (rootExtras.length) {
        chunk.extraMembers = rootExtras;
      }
    }
  });

  // Process each depth level (1 to maxDepth)
  for (var d = 1; d <= maxDepth; d++) {
    // Find tokens at this depth that have children
    tokens.forEach(function (t) {
      if (depthOf.get(t.i) === d && hasChildren(t.i)) {
        // Use contiguous version to exclude non-contiguous leaf children
        var result = getSubtreeContiguous(t.i);
        var members = result.members;
        var nonContiguousLeaves = result.nonContiguousLeaves;
        if (clauseGroup) {
          var headGroup = clauseGroup.get(t.i);
          if (headGroup !== undefined) {
            var filtered = new Set();
            members.forEach(function (m) {
              if (clauseGroup.get(m) === headGroup) {
                filtered.add(m);
              }
            });
            members = filtered;
            nonContiguousLeaves = nonContiguousLeaves.filter(function (m) {
              return clauseGroup.get(m) === headGroup;
            });
          }
        }
        var pos = t.upos || 'DEFAULT';
        var chunk = {
          headSeg: t.i,
          members: members,
          depth: d,
          pos: pos,
          extraMembers: nonContiguousLeaves
        };
        allChunks.push(chunk);

        // Register this chunk for all member tokens
        members.forEach(function (m) {
          var list = tokenToChunks.get(m);
          if (list)
            list.push({
              chunk: chunk,
              depth: d
            });
        });

        // Create singleton chunks for non-contiguous leaf children
        nonContiguousLeaves.forEach(function (leaf) {
          var singletonChunk = {
            headSeg: leaf,
            members: new Set([leaf]),
            depth: d,
            // Same depth as parent chunk
            pos:
              tokens.find(function (tok) {
                return tok.i === leaf;
              })?.upos || 'DEFAULT',
            isSingleton: true,
            isNonContiguousLeaf: true
          };
          allChunks.push(singletonChunk);
          var leafList = tokenToChunks.get(leaf);
          if (leafList)
            leafList.push({
              chunk: singletonChunk,
              depth: d
            });
        });
      }
    });
  }

  // Compute canonical chunk for each token (deepest/finest-grained chunk it belongs to)
  tokens.forEach(function (t) {
    var chunkList = tokenToChunks.get(t.i) || [];
    if (chunkList.length === 0) {
      // Token not in any chunk - assign a pseudo-chunk based on its own POS
      canonicalChunk.set(t.i, {
        headSeg: t.i,
        members: new Set([t.i]),
        depth: -1,
        pos: t.upos || 'DEFAULT',
        isSingleton: true
      });
    } else {
      // Find deepest chunk (highest depth number)
      var deepest = chunkList[0].chunk;
      for (var i = 1; i < chunkList.length; i++) {
        if (chunkList[i].depth > deepest.depth) {
          deepest = chunkList[i].chunk;
        }
      }
      canonicalChunk.set(t.i, deepest);
    }
  });
  return {
    chunks: allChunks,
    tokenToChunks: tokenToChunks,
    canonicalChunk: canonicalChunk,
    children: children,
    tokenMap: tokenMap,
    depthOf: depthOf,
    clauseGroup: clauseGroup
  };
}

// Get chunk color based on POS
export function initializeDependencyPopup() {
  dependencyPopupState.GRAMMAR_TYPES = Object.keys(presentationState.GRAMMAR_TYPE_COLORS || {});
  dependencyPopupState.DEBUG_CAPTURE_PROTOTYPE_ENABLED = false;
  dependencyPopupState.displaySettings = {
    grammarTypes: {},
    udOverlay: true,
    // On/off toggle for clause-based UD arrows
    chunkHighlight: true,
    // On/off toggle for phrase/clause span highlighting
    nerOverlay: true,
    // On/off toggle for NER label overlay
    islandDepTree: false,
    // DISABLED FOR DEPLOYMENT - island-based hover overlay
    connectedIslands: false,
    // DISABLED FOR DEPLOYMENT - Group and highlight connected islands
    connectedIslandsAclGate: false,
    // DISABLED FOR DEPLOYMENT - Merge connected islands unless head is VERB+acl
    contextWindow: false,
    // DISABLED FOR DEPLOYMENT - context window chunking algorithm
    contextWindowSize: 10,
    // Token count for context window size
    bottomUpChunk: true,
    // DEPLOYMENT: Always on when UD arrows/chunks enabled
    bottomUpCascade: true,
    // Recurse through descendants and highlight every descendant surface
    bottomUpChunkThreshold: 5,
    // Distance threshold for bottom-up chunking
    linearClauseSplit: false,
    // Optional linear clause splitting (left-to-right)
    branchDepthMin: 1,
    // Minimum head-chain depth to count as a branch
    clauseDepthDrop: 3,
    // Depth discontinuity threshold for postpass clause splits
    depTreeView: false,
    udPopup: false,
    pronunciation: false,
    grammarPopup: true,
    dictPopup: true,
    llmDecomp: false,
    comments: false,
    // DISABLED FOR DEPLOYMENT
    subsegmentPopups: false,
    // DISABLED FOR DEPLOYMENT - subsegment popups
    debugCapture: false,
    stripPunctuation: false,
    manualSentenceSegmentation: false,
    pdfOcrCleanup: false,
    // sqliteDictMode removed � SQLite is always on
    fuzzyMaxEditDistance: 3,
    mergeGreedy: true,
    splitDictFill: false,
    posOverride: true,
    llmGloss: false,
    orthBreakdown: false,
    geminiNer: false,
    stanzaNer: true,
    collapseNerUd: true,
    dpResegment: true,
    lmWeights: {
      oovPenalty: 10.0,
      dictNoLmDiscount: 1.0,
      unigramWeight: 0.2,
      knownWordBaseCost: 1.0,
      unknownWordBaseCost: 5.0,
      bigramWeight: 0.1
    }
  };
  dependencyPopupState.LM_WEIGHT_DEFAULTS = {
    oovPenalty: 10.0,
    dictNoLmDiscount: 1.0,
    unigramWeight: 0.2,
    knownWordBaseCost: 1.0,
    unknownWordBaseCost: 5.0,
    bigramWeight: 0.1
  };
  dependencyPopupState.LM_WEIGHT_FIELDS = [
    {
      key: 'oovPenalty',
      label: 'OOV syllable penalty',
      param: 'lm_oov_penalty',
      step: '0.1'
    },
    {
      key: 'dictNoLmDiscount',
      label: 'Dict no-LM discount',
      param: 'lm_dict_no_lm_discount',
      step: '0.05'
    },
    {
      key: 'unigramWeight',
      label: 'Unigram weight',
      param: 'lm_unigram_weight',
      step: '0.05'
    },
    {
      key: 'knownWordBaseCost',
      label: 'Known word base cost',
      param: 'lm_known_base_cost',
      step: '0.1'
    },
    {
      key: 'unknownWordBaseCost',
      label: 'Unknown word base cost',
      param: 'lm_unknown_base_cost',
      step: '0.1'
    },
    {
      key: 'bigramWeight',
      label: 'Bigram weight',
      param: 'lm_bigram_weight',
      step: '0.05'
    }
  ];
  dependencyPopupState.CHUNK_POS_COLORS = {
    ADJ: {
      bg: '#fde68a',
      border: 'rgba(251, 191, 36, 0.5)'
    },
    ADP: {
      bg: '#e0f2fe',
      border: 'rgba(125, 211, 252, 0.5)'
    },
    ADV: {
      bg: '#fee2e2',
      border: 'rgba(252, 165, 165, 0.5)'
    },
    AUX: {
      bg: '#e0e7ff',
      border: 'rgba(165, 180, 252, 0.5)'
    },
    CCONJ: {
      bg: '#cffafe',
      border: 'rgba(103, 232, 249, 0.5)'
    },
    DET: {
      bg: '#f1f5f9',
      border: 'rgba(203, 213, 225, 0.5)'
    },
    INTJ: {
      bg: '#fcd34d',
      border: 'rgba(251, 191, 36, 0.5)'
    },
    NOUN: {
      bg: '#bbf7d0',
      border: 'rgba(74, 222, 128, 0.5)'
    },
    NUM: {
      bg: '#f5d0fe',
      border: 'rgba(240, 171, 252, 0.5)'
    },
    PART: {
      bg: '#f4f4f5',
      border: 'rgba(212, 212, 216, 0.5)'
    },
    PRON: {
      bg: '#e2e8f0',
      border: 'rgba(148, 163, 184, 0.5)'
    },
    PROPN: {
      bg: '#c7d2fe',
      border: 'rgba(165, 180, 252, 0.5)'
    },
    PUNCT: {
      bg: '#e5e7eb',
      border: 'rgba(156, 163, 175, 0.5)'
    },
    SCONJ: {
      bg: '#bae6fd',
      border: 'rgba(125, 211, 252, 0.5)'
    },
    SYM: {
      bg: '#f3e8ff',
      border: 'rgba(216, 180, 254, 0.5)'
    },
    VERB: {
      bg: '#fda4af',
      border: 'rgba(251, 113, 133, 0.5)'
    },
    X: {
      bg: '#d1d5db',
      border: 'rgba(156, 163, 175, 0.5)'
    },
    ROOT: {
      bg: '#fbbf24',
      border: 'rgba(217, 119, 6, 0.6)'
    },
    DEFAULT: {
      bg: '#e5e7eb',
      border: 'rgba(156, 163, 175, 0.5)'
    }
  };

  // Cache for computed chunks
  dependencyPopupState.latestChunks = null;
  return true;
}
