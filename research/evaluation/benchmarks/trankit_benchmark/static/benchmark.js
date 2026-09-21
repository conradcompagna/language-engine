const gpuOptRunBtn = document.getElementById("gpuOptRunBtn");
    const xlmLoadProbeBtn = document.getElementById("xlmLoadProbeBtn");
    const langLoadProbeBtn = document.getElementById("langLoadProbeBtn");
    const fullLoadProbeBtn = document.getElementById("fullLoadProbeBtn");
    const topStatus = document.getElementById("topStatus");
    const gpuOptStatus = document.getElementById("gpuOptStatus");
    const gpuStatus = document.getElementById("gpuStatus");
    const summary = document.getElementById("summary");
    const metricsOut = document.getElementById("metricsOut");
    const cpuOut = document.getElementById("cpuOut");
    const gpuOut = document.getElementById("gpuOut");
    const diffOut = document.getElementById("diffOut");
    const probeSummary = document.getElementById("probeSummary");
    const probeOut = document.getElementById("probeOut");
    const rawOut = document.getElementById("rawOut");

    function fmtBytes(n) {
      if (typeof n !== "number" || !isFinite(n) || n < 0) return "n/a";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let v = n;
      let i = 0;
      while (v >= 1024 && i < units.length - 1) {
        v /= 1024;
        i++;
      }
      return `${v.toFixed(2)} ${units[i]}`;
    }

    function fmtSeconds(n) {
      if (typeof n !== "number" || !isFinite(n)) return "n/a";
      return `${n.toFixed(3)} s`;
    }

    function pretty(value) {
      return JSON.stringify(value, null, 2);
    }

    function metricBox(name, value) {
      return `<div class="metric"><div class="metric-name">${name}</div><div class="metric-value">${value}</div></div>`;
    }

    function metricPanel(title, boxes) {
      return `<section class="metric-panel"><h3>${title}</h3><div class="metric-panel-grid">${boxes.join("")}</div></section>`;
    }

    function metricSplit(leftTitle, leftBoxes, rightTitle, rightBoxes) {
      return `<div class="metric-split">${metricPanel(leftTitle, leftBoxes)}${metricPanel(rightTitle, rightBoxes)}</div>`;
    }

    function metricDetails(title, contentHtml) {
      return `<details class="metric-details"><summary>${title}</summary>${contentHtml}</details>`;
    }

    function cpuOptQuantCount(load, field) {
      const report = load && load.cpu_opt && load.cpu_opt.optimization_report;
      if (!report) return "n/a";
      if (field === "xlmr") {
        const q = report.xlmr_quantization || {};
        if (typeof q.quantized_count === "number") return String(q.quantized_count);
        if (q.cache && typeof q.cache.quantized_count === "number") return String(q.cache.quantized_count);
        return "n/a";
      }
      const rows = Array.isArray(report.seq2seq_quantization) ? report.seq2seq_quantization : [];
      if (report.seq2seq_quantization && report.seq2seq_quantization.skipped) return "0 (skipped)";
      let total = 0;
      let seen = false;
      rows.forEach((row) => {
        if (row && typeof row.quantized_count === "number") {
          total += row.quantized_count;
          seen = true;
        } else if (row && row.cache && typeof row.cache.quantized_count === "number") {
          total += row.cache.quantized_count;
          seen = true;
        }
      });
      return seen ? String(total) : "n/a";
    }

    function cpuOptReport(load) {
      return load && load.cpu_opt && load.cpu_opt.optimization_report ? load.cpu_opt.optimization_report : {};
    }

    function cpuOptAdapterStatus(load) {
      const report = cpuOptReport(load);
      const q = report.xlmr_quantization || {};
      const skipped = Number(q.skipped_adapter_count || 0);
      const quantized = Number(report.xlmr_adapter_dynamic_int8_count || 0);
      return `${skipped} skipped / ${quantized} quantized`;
    }

    function cpuOptEvalStatus(load) {
      const status = cpuOptReport(load).eval_status || {};
      if (status.embedding_eval && status.xlmr_eval) return "yes";
      if (status.embedding_eval || status.xlmr_eval) return "partial";
      return "no";
    }

    function cpuOptCompileStatus(load) {
      const value = cpuOptReport(load).torch_compile || {};
      return String(value.status || (value.ok ? "kept" : value.error ? "rejected" : "skipped"));
    }

    function cpuOptBf16Status(load) {
      const report = cpuOptReport(load);
      if (report.bf16_status) return String(report.bf16_status);
      const probe = report.bf16_probe || {};
      if (probe.supported) return "available";
      return "skipped";
    }

    function cpuOptHiddenStateStatus(load) {
      const patch = load && load.cpu_opt && load.cpu_opt.xlmr_load_patch_report;
      const report = load && load.cpu_opt && load.cpu_opt.optimization_report && load.cpu_opt.optimization_report.xlmr_hidden_state_outputs;
      if (patch && patch.installed === false) return "patch failed";
      if (report && typeof report.changed_attrs === "number") return `disabled (${report.changed_attrs} attrs)`;
      if (patch && patch.installed) return "load patched";
      return "n/a";
    }

    function renderStatus(status) {
      const gpu = status.gpu || {};
      const gpuOpt = status.onnx_cpu || {};
      gpuOptStatus.textContent = `${gpuOpt.state || "not started"}${gpuOpt.pid ? " pid " + gpuOpt.pid : ""}`;
      gpuStatus.textContent = `${gpu.state || "unknown"}${gpu.pid ? " pid " + gpu.pid : ""}`;
      if (gpuOpt.state === "error" && gpuOpt.error) {
        gpuOptStatus.textContent += ` error: ${gpuOpt.error}`;
      }
      const optReady = gpuOpt.state === "ready" && gpu.state === "ready";
      if (gpuOpt.state === "error" || gpu.state === "error") {
        topStatus.textContent = "Worker error";
      } else {
        topStatus.textContent = optReady ? "Workers ready" : "Workers loading";
      }
    }

    async function refreshStatus() {
      try {
        const res = await fetch("/api/status", { cache: "no-store" });
        renderStatus(await res.json());
      } catch (err) {
        topStatus.textContent = "Status unavailable";
      }
    }

    function responseTokenCount(response) {
      const devices = response.devices || {};
      const candidates = [devices.onnx_cpu, devices.cpu_opt, devices.gpu_opt, devices.cpu, devices.gpu];
      for (const device of candidates) {
        const counts = device && device.metrics && device.metrics.annotation_counts;
        const count = counts && counts.token_count;
        if (Number.isFinite(Number(count))) return String(count);
      }
      return "0";
    }

    function taskStageTime(metrics, stageName) {
      const stages = metrics && metrics.task_breakdown && metrics.task_breakdown.stages;
      const row = stages && stages[stageName];
      if (!row || !row.count) return "n/a";
      const seconds = Number(row.exclusive_seconds);
      const suffix = row.count > 1 ? ` (${row.count}x)` : "";
      return Number.isFinite(seconds) ? `${fmtSeconds(seconds)}${suffix}` : "n/a";
    }

    function taskStageSeconds(metrics, stageName) {
      const stages = metrics && metrics.task_breakdown && metrics.task_breakdown.stages;
      const row = stages && stages[stageName];
      const seconds = row && row.count ? Number(row.exclusive_seconds) : NaN;
      return Number.isFinite(seconds) ? seconds : 0;
    }

    function taskStageRow(metrics, stageName) {
      const stages = metrics && metrics.task_breakdown && metrics.task_breakdown.stages;
      return stages && stages[stageName] ? stages[stageName] : {};
    }

    function taskBatchCount(metrics, stageName) {
      const row = taskStageRow(metrics, stageName);
      const direct = Number(row.batch_count || 0);
      if (direct > 0) return direct;
      return Math.max(
        Number(row.xlm_call_count || 0),
        Number(row.seq2seq_call_count || 0),
        Number(row.head_call_count || 0)
      );
    }

    function taskBatchText(metrics, stageName) {
      const row = taskStageRow(metrics, stageName);
      const count = taskBatchCount(metrics, stageName);
      if (!count) return "n/a";
      const items = Number(row.batch_items || 0);
      const avg = items && count ? (items / count).toFixed(1) : "n/a";
      const min = row.batch_min_items == null ? "n/a" : String(row.batch_min_items);
      const max = row.batch_max_items == null ? "n/a" : String(row.batch_max_items);
      return `${count} batches / avg ${avg} / min ${min} / max ${max}`;
    }

    function taskShapeText(metrics, stageName) {
      const row = taskStageRow(metrics, stageName);
      const count = taskBatchCount(metrics, stageName);
      if (!count) return "n/a";
      const maxLen = row.batch_max_padded_length == null ? "n/a" : String(row.batch_max_padded_length);
      const padded = Number(row.batch_padded_units || 0);
      const real = Number(row.batch_real_units || 0);
      const fake = Number(row.batch_padding_units || 0);
      const fakeText = real ? ` / fake pad ${fake}` : "";
      return `max seq ${maxLen} / total padded units ${padded || "n/a"}${fakeText}`;
    }

    function taskBatchPaddingText(metrics, stageName) {
      const row = taskStageRow(metrics, stageName);
      const details = Array.isArray(row.batch_padding_details) ? row.batch_padding_details : [];
      if (!details.length) return "n/a";
      return details.map((item) => {
        const index = Number(item.index || 0);
        const items = Number(item.items || 0);
        const maxLen = Number(item.max_len || 0);
        const padded = Number(item.padded_units || 0);
        const fake = item.padding_units == null ? null : Number(item.padding_units);
        const fakePart = Number.isFinite(fake) ? `, fake ${fake}` : "";
        return `#${index}: ${items}x${maxLen}=${padded}${fakePart}`;
      }).join(" | ");
    }

    function dynamicBatchSummary(metrics) {
      const events = Array.isArray(metrics && metrics.onnx_dynamic_batch_events) ? metrics.onnx_dynamic_batch_events : [];
      if (!events.length) return metrics && metrics.onnx_dynamic_batching ? "dynamic" : "n/a";
      return events.map((event) => {
        const kind = String(event.kind || "?");
        const selected = event.selected_batch_size == null ? "?" : String(event.selected_batch_size);
        const requested = event.requested_batch_size == null ? "?" : String(event.requested_batch_size);
        const plan = event.plan && event.plan.selected ? event.plan.selected : {};
        const fake = plan.padding_units == null ? "?" : String(plan.padding_units);
        return `${kind}:${selected}/${requested} fake ${fake}`;
      }).join(" | ");
    }

    function ortTuningSummary(runtime, report) {
      const tuning = (runtime && runtime.ort_tuning) || (report && report.ort_tuning) || {};
      if (tuning.applied && tuning.profile) {
        const profile = tuning.profile || {};
        const name = String(profile.name || "applied");
        const intra = profile.intra_op_num_threads == null ? "default" : String(profile.intra_op_num_threads);
        const inter = profile.inter_op_num_threads == null ? "default" : String(profile.inter_op_num_threads);
        const mem = profile.enable_mem_pattern === false ? "mem-pattern off" : "mem-pattern on";
        return `${name} / intra ${intra} / inter ${inter} / ${mem}`;
      }
      if (tuning.loaded && !tuning.applied) {
        return `default (${String(tuning.reason || tuning.error || "not applied")})`;
      }
      return "default";
    }

    function taskModelCallText(metrics, stageName) {
      const row = taskStageRow(metrics, stageName);
      const parts = [];
      const xlm = Number(row.xlm_call_count || 0);
      const head = Number(row.head_call_count || 0);
      const seq2seq = Number(row.seq2seq_call_count || 0);
      if (xlm) parts.push(`XLM:${xlm}`);
      if (head) parts.push(`head:${head}`);
      if (seq2seq) parts.push(`seq2seq:${seq2seq}`);
      if (!parts.length) return "n/a";
      const seconds = Number(row.model_call_seconds || 0);
      const suffix = Number.isFinite(seconds) && seconds > 0 ? ` / call wall ${fmtSeconds(seconds)}` : "";
      return `${parts.join(" ")}${suffix}`;
    }

    function onnxTaskRuntime(runtime, taskName) {
      const rows = runtime && runtime.request_by_key ? runtime.request_by_key : {};
      const out = {
        count: 0,
        total_seconds: 0,
        preprocess_seconds: 0,
        session_seconds: 0,
        postprocess_seconds: 0
      };
      Object.keys(rows).forEach((key) => {
        if (!key.endsWith(`:${taskName}`)) return;
        const row = rows[key] || {};
        out.count += Number(row.count || 0);
        out.total_seconds += Number(row.total_seconds || 0);
        out.preprocess_seconds += Number(row.preprocess_seconds || 0);
        out.session_seconds += Number(row.session_seconds || 0);
        out.postprocess_seconds += Number(row.postprocess_seconds || 0);
      });
      return out;
    }

    function taskPanel(label, stageName, onnxTaskName, cpuM, gpuM, runtime) {
      const cpuTotal = taskStageSeconds(cpuM, stageName);
      const gpuTotal = taskStageTime(gpuM, stageName);
      const cpuBoxes = [
        metricBox("Total", cpuTotal ? taskStageTime(cpuM, stageName) : "n/a"),
        metricBox("Batches", taskBatchText(cpuM, stageName)),
        metricBox("Shapes", taskShapeText(cpuM, stageName)),
        metricBox("Padding / batch", taskBatchPaddingText(cpuM, stageName)),
        metricBox("Model calls", taskModelCallText(cpuM, stageName))
      ];
      if (onnxTaskName) {
        const rt = onnxTaskRuntime(runtime, onnxTaskName);
        const handoff = rt.preprocess_seconds + rt.postprocess_seconds;
        const nonOnnx = Math.max(0, cpuTotal - rt.total_seconds);
        cpuBoxes.push(metricBox("ONNX runtime", rt.count ? `${fmtSeconds(rt.total_seconds)} (${rt.count}x)` : "n/a"));
        cpuBoxes.push(metricBox("ORT session", rt.count ? fmtSeconds(rt.session_seconds) : "n/a"));
        cpuBoxes.push(metricBox("ONNX handoff", rt.count ? fmtSeconds(handoff) : "n/a"));
        cpuBoxes.push(metricBox("PyTorch/other", cpuTotal ? fmtSeconds(nonOnnx) : "n/a"));
      } else {
        cpuBoxes.push(metricBox("ONNX runtime", "n/a"));
        cpuBoxes.push(metricBox("ORT session", "n/a"));
        cpuBoxes.push(metricBox("ONNX handoff", "n/a"));
        cpuBoxes.push(metricBox("PyTorch/other", cpuTotal ? fmtSeconds(cpuTotal) : "n/a"));
      }
      const gpuBoxes = [
        metricBox("Total", gpuTotal),
        metricBox("Batches", taskBatchText(gpuM, stageName)),
        metricBox("Shapes", taskShapeText(gpuM, stageName)),
        metricBox("Padding / batch", taskBatchPaddingText(gpuM, stageName)),
        metricBox("Model calls", taskModelCallText(gpuM, stageName))
      ];
      return `<section class="metric-panel"><h3>${label}</h3>${metricSplit("ONNX CPU", cpuBoxes, "Regular GPU", gpuBoxes)}</section>`;
    }

    function taskBreakdownByTask(cpuM, gpuM, runtime) {
      return [
        taskPanel("Tokenization", "tokenization", "tokenizer", cpuM, gpuM, runtime),
        taskPanel("MWT expansion", "mwt_expansion", null, cpuM, gpuM, runtime),
        taskPanel("POS / dependency", "posdep_tagging", "tagger", cpuM, gpuM, runtime),
        taskPanel("Lemmatization", "lemmatization", null, cpuM, gpuM, runtime),
        taskPanel("NER", "ner", "ner", cpuM, gpuM, runtime)
      ].join("");
    }

    function renderSummary(response) {
      const cpu = response.devices && response.devices.cpu;
      const gpu = response.devices && response.devices.gpu;
      const cpuM = cpu && cpu.metrics;
      const gpuM = gpu && gpu.metrics;
      summary.innerHTML = [
        metricBox("CPU time", fmtSeconds(cpuM && cpuM.elapsed_seconds)),
        metricBox("GPU time", fmtSeconds(gpuM && gpuM.elapsed_seconds)),
        metricBox("CPU peak RSS delta", fmtBytes(cpuM && cpuM.rss_peak_sampled_delta_bytes)),
        metricBox("GPU peak allocated", fmtBytes(gpuM && gpuM.gpu_allocator_max_allocated_bytes)),
        metricBox("CPU load RSS", fmtBytes(response.load && response.load.cpu && response.load.cpu.rss_total_load_delta_bytes)),
        metricBox("GPU load RSS", fmtBytes(response.load && response.load.gpu && response.load.gpu.rss_total_load_delta_bytes)),
        metricBox("GPU load reserved", fmtBytes(response.load && response.load.gpu && response.load.gpu.gpu_after_load && response.load.gpu.gpu_after_load.reserved_bytes)),
        metricBox("Tokens", responseTokenCount(response))
      ].join("");
    }

    function renderCpuOptSummary(response) {
      const cpu = response.devices && response.devices.cpu_opt;
      const gpu = response.devices && response.devices.gpu;
      const cpuM = cpu && cpu.metrics;
      const gpuM = gpu && gpu.metrics;
      const comparison = response.comparison || {};
      const load = response.load || {};
      const selection = response.cpu_opt_selection || {};
      const cpuStatus = response.worker_status && response.worker_status.cpu_opt ? response.worker_status.cpu_opt : {};
      const ratio = typeof comparison.cpu_opt_vs_gpu_ratio === "number" ? `${comparison.cpu_opt_vs_gpu_ratio.toFixed(3)}x GPU` : "n/a";
      summary.innerHTML = [
        metricBox("Optimized CPU time", fmtSeconds(cpuM && cpuM.elapsed_seconds)),
        metricBox("Regular GPU time", fmtSeconds(gpuM && gpuM.elapsed_seconds)),
        metricBox("CPU/GPU ratio", ratio),
        metricBox("CPU worker", String(cpuStatus.state || (cpu && cpu.ok === false ? "error" : "n/a"))),
        metricBox("Output match", comparison.output_match ? "yes" : "no"),
        metricBox("CPU profile", String((cpuM && cpuM.cpu_opt_profile) || selection.selected_profile || "n/a")),
        metricBox("CPU threads", String((cpuM && cpuM.cpu_opt_thread_count) || selection.selected_thread_count || "n/a")),
        metricBox("Sequence bucket", String((cpuM && cpuM.sequence_bucket) || "n/a")),
        metricBox("XLM-R INT8 modules", cpuOptQuantCount(load, "xlmr")),
        metricBox("Adapter modules", cpuOptAdapterStatus(load)),
        metricBox("Seq2seq INT8 modules", cpuOptQuantCount(load, "seq2seq")),
        metricBox("Hidden states", cpuOptHiddenStateStatus(load)),
        metricBox("Eval mode", cpuOptEvalStatus(load)),
        metricBox("torch.compile", cpuOptCompileStatus(load)),
        metricBox("BF16", cpuOptBf16Status(load)),
        metricBox("CPU opt setup", fmtSeconds(selection.setup_seconds)),
        metricBox("CPU opt load", fmtSeconds(load.cpu_opt && load.cpu_opt.load_seconds)),
        metricBox("CPU opt apply", fmtSeconds(load.cpu_opt && load.cpu_opt.optimization_seconds)),
        metricBox("CPU opt tune", fmtSeconds(load.cpu_opt && load.cpu_opt.startup_tuning_report && load.cpu_opt.startup_tuning_report.elapsed_seconds)),
        metricBox("GPU load", fmtSeconds(load.gpu && load.gpu.load_seconds)),
        metricBox("GC suppressed", String((cpuM && cpuM.gc_collect_calls_suppressed) || 0)),
        metricBox("CUDA cache suppressed", String((cpuM && cpuM.cuda_empty_cache_calls_suppressed) || 0)),
        metricBox("Tokens", responseTokenCount(response))
      ].join("");
    }

    function gpuOptReport(load) {
      return load && load.gpu_opt && load.gpu_opt.optimization_report ? load.gpu_opt.optimization_report : {};
    }

    function gpuOptEvalStatus(load) {
      const status = gpuOptReport(load).eval_status || {};
      if (status.embedding_eval && status.xlmr_eval) return "yes";
      if (status.embedding_eval || status.xlmr_eval) return "partial";
      return "no";
    }

    function gpuOptHiddenStateStatus(load) {
      const report = gpuOptReport(load);
      const status = report.xlmr_hidden_state_status || {};
      if (status.disabled === true) return "yes";
      if (status.disabled === false) return "no";
      return "n/a";
    }

    function gpuOptFp16Status(load) {
      const fp16 = gpuOptReport(load).fp16_coverage || {};
      if (fp16.error) return `error: ${fp16.error}`;
      if (fp16.all_checked_float_params_fp16 === true) return "yes";
      if (fp16.all_checked_float_params_fp16 === false) return "partial/no";
      return "n/a";
    }

    function gpuOptTf32Status(load) {
      const backend = gpuOptReport(load).backend || {};
      const mm = backend.cuda_matmul_allow_tf32 === true;
      const cudnn = backend.cudnn_allow_tf32 === true;
      return `${mm ? "matmul yes" : "matmul n/a"} / ${cudnn ? "cudnn yes" : "cudnn n/a"}`;
    }

    function gpuOptCompileStatus(load) {
      const compile = gpuOptReport(load).torch_compile || {};
      return String(compile.status || (compile.ok ? "kept" : compile.error ? "rejected" : "skipped"));
    }

    function syncPointSummary(metrics) {
      const sync = metrics && metrics.sync_points ? metrics.sync_points : {};
      const calls = sync.calls || {};
      const parts = [];
      ["cpu", "numpy", "tolist", "item"].forEach((name) => {
        const row = calls[name] || {};
        parts.push(`${name}:${row.count || 0}`);
      });
      return parts.join(" ");
    }

    function renderGpuOptSummary(response) {
      const gpuOpt = response.devices && response.devices.gpu_opt;
      const gpu = response.devices && response.devices.gpu;
      const optM = gpuOpt && gpuOpt.metrics;
      const gpuM = gpu && gpu.metrics;
      const comparison = response.comparison || {};
      const load = response.load || {};
      const status = response.worker_status && response.worker_status.gpu_opt ? response.worker_status.gpu_opt : {};
      const speedup = typeof comparison.gpu_opt_speedup_ratio === "number" ? `${comparison.gpu_opt_speedup_ratio.toFixed(3)}x` : "n/a";
      summary.innerHTML = [
        metricBox("Optimized GPU time", fmtSeconds(optM && optM.elapsed_seconds)),
        metricBox("Regular GPU time", fmtSeconds(gpuM && gpuM.elapsed_seconds)),
        metricBox("Speedup ratio", speedup),
        metricBox("GPU opt worker", String(status.state || (gpuOpt && gpuOpt.ok === false ? "error" : "n/a"))),
        metricBox("Output match", comparison.output_match ? "yes" : "no"),
        metricBox("GPU opt profile", String((optM && optM.gpu_opt_profile) || (load.gpu_opt && load.gpu_opt.gpu_opt_profile) || "n/a")),
        metricBox("Hidden states disabled", gpuOptHiddenStateStatus(load)),
        metricBox("Eval mode", gpuOptEvalStatus(load)),
        metricBox("FP16 coverage", gpuOptFp16Status(load)),
        metricBox("TF32 enabled", gpuOptTf32Status(load)),
        metricBox("torch.compile", gpuOptCompileStatus(load)),
        metricBox("Sequence bucket", String((optM && optM.sequence_bucket) || "n/a")),
        metricBox("GC suppressed", String((optM && optM.gc_collect_calls_suppressed) || 0)),
        metricBox("CUDA cache suppressed", String((optM && optM.cuda_empty_cache_calls_suppressed) || 0)),
        metricBox("GPU allocated peak", fmtBytes(optM && optM.gpu_allocator_max_allocated_bytes)),
        metricBox("GPU reserved peak", fmtBytes(optM && optM.gpu_allocator_max_reserved_bytes)),
        metricBox("GPU opt load", fmtSeconds(load.gpu_opt && load.gpu_opt.load_seconds)),
        metricBox("GPU opt setup", fmtSeconds(load.gpu_opt && load.gpu_opt.optimization_seconds)),
        metricBox("Sync points", syncPointSummary(optM)),
        metricBox("Tokens", responseTokenCount(response))
      ].join("");
    }

    function renderOnnxSummary(response) {
      const cpu = response.devices && response.devices.onnx_cpu;
      const gpu = response.devices && response.devices.gpu;
      const cpuM = cpu && cpu.metrics;
      const gpuM = gpu && gpu.metrics;
      const comparison = response.comparison || {};
      const load = response.load || {};
      const report = load.onnx_cpu && load.onnx_cpu.onnx_report ? load.onnx_cpu.onnx_report : {};
      const runtime = cpuM && cpuM.onnx_runtime ? cpuM.onnx_runtime : {};
      const requestOnnxCalls = runtime.request_run_count != null ? runtime.request_run_count : runtime.run_count;
      const ratio = typeof comparison.onnx_cpu_vs_gpu_ratio === "number" ? `${comparison.onnx_cpu_vs_gpu_ratio.toFixed(3)}x GPU` : "n/a";
      const onnxBoxes = [
        metricBox("Time", fmtSeconds(cpuM && cpuM.elapsed_seconds)),
        metricBox("Profile", String((cpuM && cpuM.onnx_profile) || (load.onnx_cpu && load.onnx_cpu.onnx_profile) || "n/a")),
        metricBox("Session", runtime.onnx_session ? "1 shared" : "n/a"),
        metricBox("ORT profile", ortTuningSummary(runtime, report)),
        metricBox("Adapter packs", `${report.adapter_pack_count || runtime.loaded_pack_count || 0}/${report.task_count || 0}`),
        metricBox("Missing packs", String(report.missing_count || 0)),
        metricBox("Tok batch", String((cpuM && cpuM.onnx_tok_batch_size) || (load.onnx_cpu && load.onnx_cpu.onnx_tok_batch_size) || "n/a")),
        metricBox("POS/NER batch", String((cpuM && cpuM.onnx_tag_batch_size) || (load.onnx_cpu && load.onnx_cpu.onnx_tag_batch_size) || "n/a")),
        metricBox("XLM batch planner", dynamicBatchSummary(cpuM)),
        metricBox("Seq2seq planner", (cpuM && cpuM.onnx_seq2seq_dynamic_batching) ? "dynamic" : "off"),
        metricBox("Tok padding", (cpuM && cpuM.onnx_tokenizer_dynamic_padding) ? "dynamic" : ((load.onnx_cpu && load.onnx_cpu.onnx_tokenizer_padding_report && load.onnx_cpu.onnx_tokenizer_padding_report.installed) ? "dynamic" : "n/a")),
        metricBox("POS/NER bucketing", (cpuM && cpuM.onnx_tagger_ner_length_bucketing) ? "length" : ((load.onnx_cpu && load.onnx_cpu.onnx_tagger_ner_bucketing_report && load.onnx_cpu.onnx_tagger_ner_bucketing_report.installed) ? "length" : "n/a")),
        metricBox("Calls/request", String(requestOnnxCalls || 0)),
        metricBox("Calls/lifetime", String(runtime.run_count || 0)),
        metricBox("Latent RSS", fmtBytes(load.onnx_cpu && load.onnx_cpu.rss_after_load_bytes)),
        metricBox("RSS spike", fmtBytes(cpuM && cpuM.rss_peak_sampled_delta_bytes)),
        metricBox("Setup", fmtSeconds(load.onnx_cpu && load.onnx_cpu.optimization_seconds)),
        metricBox("Load", fmtSeconds(load.onnx_cpu && load.onnx_cpu.load_seconds)),
        metricBox("GC suppressed", String((cpuM && cpuM.gc_collect_calls_suppressed) || 0))
      ];
      const gpuBoxes = [
        metricBox("Time", fmtSeconds(gpuM && gpuM.elapsed_seconds)),
        metricBox("Latent RSS", fmtBytes(load.gpu && load.gpu.rss_after_load_bytes)),
        metricBox("Latent VRAM", fmtBytes(load.gpu && load.gpu.gpu_after_load && load.gpu.gpu_after_load.allocated_bytes)),
        metricBox("RSS spike", fmtBytes(gpuM && gpuM.rss_peak_sampled_delta_bytes)),
        metricBox("VRAM peak", fmtBytes(gpuM && gpuM.gpu_allocator_max_allocated_bytes)),
        metricBox("Load", fmtSeconds(load.gpu && load.gpu.load_seconds))
      ];
      summary.innerHTML = [
        metricBox("CPU/GPU ratio", ratio),
        metricBox("Output match", comparison.output_match ? "yes" : "no"),
        metricBox("Tokens", responseTokenCount(response)),
        metricSplit("ONNX CPU", onnxBoxes, "Regular GPU", gpuBoxes),
        metricDetails("Task timing breakdown", taskBreakdownByTask(cpuM, gpuM, runtime))
      ].join("");
    }

    function stageSeconds(result, predicate) {
      if (!result || !Array.isArray(result.stages)) return 0;
      return result.stages.reduce((sum, stage) => {
        if (!stage || !predicate(stage)) return sum;
        const seconds = Number(stage.elapsed_seconds);
        return sum + (Number.isFinite(seconds) ? seconds : 0);
      }, 0);
    }

    function topStageText(result) {
      if (!result || !Array.isArray(result.stages)) return "No stages.";
      return result.stages
        .filter((stage) => stage && !String(stage.name || "").endsWith("_total"))
        .slice()
        .sort((a, b) => Number(b.elapsed_seconds || 0) - Number(a.elapsed_seconds || 0))
        .slice(0, 12)
        .map((stage) => `${fmtSeconds(Number(stage.elapsed_seconds || 0)).padStart(10)}  ${stage.name}`)
        .join("\n");
    }

    function renderLoadProbe(response) {
      const cpu = response.devices && response.devices.cpu;
      const gpu = response.devices && response.devices.gpu;
      const cpuImport = stageSeconds(cpu, (s) => String(s.name || "").startsWith("import_"));
      const gpuImport = stageSeconds(gpu, (s) => String(s.name || "").startsWith("import_"));
      const cpuLoad = stageSeconds(cpu, (s) => ["load_shared_xlm_only", "load_selected_language_modules", "load_full_app_trankit_pipeline"].includes(String(s.name || "")));
      const gpuLoad = stageSeconds(gpu, (s) => ["load_shared_xlm_only", "load_selected_language_modules", "load_full_app_trankit_pipeline"].includes(String(s.name || "")));
      const cpuFirstInference = stageSeconds(cpu, (s) => String(s.name || "") === "first_inference_after_cold_load");
      const gpuFirstInference = stageSeconds(gpu, (s) => String(s.name || "") === "first_inference_after_cold_load");
      const cpuError = cpu && cpu.ok === false ? String(cpu.error || "probe failed") : "";
      const gpuError = gpu && gpu.ok === false ? String(gpu.error || "probe failed") : "";
      probeSummary.innerHTML = [
        metricBox("Probe wall time", fmtSeconds(response.elapsed_seconds)),
        metricBox("CPU process wall", fmtSeconds(cpu && cpu.probe_process_wall_seconds)),
        metricBox("GPU process wall", fmtSeconds(gpu && gpu.probe_process_wall_seconds)),
        metricBox("CPU imports", fmtSeconds(cpuImport)),
        metricBox("GPU imports", fmtSeconds(gpuImport)),
        metricBox("CPU Trankit load", fmtSeconds(cpuLoad)),
        metricBox("GPU Trankit load", fmtSeconds(gpuLoad)),
        metricBox("CPU first inference", fmtSeconds(cpuFirstInference)),
        metricBox("GPU first inference", fmtSeconds(gpuFirstInference)),
        metricBox("CPU loaded langs", String((cpu && cpu.added_lang_count) || 0)),
        metricBox("GPU loaded langs", String((gpu && gpu.added_lang_count) || 0)),
        metricBox("CPU status", cpuError || (cpu && cpu.ok ? "ok" : "missing")),
        metricBox("GPU status", gpuError || (gpu && gpu.ok ? "ok" : "missing"))
      ].join("");
      probeOut.textContent = [
        "Probe mode:",
        response.description || response.mode || "",
        "",
        "CPU loaded:",
        cpu && cpu.loaded_description ? cpu.loaded_description : "",
        "",
        "GPU loaded:",
        gpu && gpu.loaded_description ? gpu.loaded_description : "",
        "",
        "CPU slowest stages:",
        topStageText(cpu),
        cpuError ? "\nCPU error:\n" + cpuError : "",
        "",
        "GPU slowest stages:",
        topStageText(gpu),
        gpuError ? "\nGPU error:\n" + gpuError : "",
        "",
        "Raw JSON:",
        pretty(response)
      ].join("\n");
    }

    function showPane(paneId) {
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.toggle("active", t.dataset.pane === paneId);
      });
      document.querySelectorAll(".pane").forEach((p) => {
        p.classList.toggle("active", p.id === paneId);
      });
    }

    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        document.querySelectorAll(".pane").forEach((p) => p.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(tab.dataset.pane).classList.add("active");
      });
    });

    gpuOptRunBtn.addEventListener("click", async () => {
      gpuOptRunBtn.disabled = true;
      gpuOptRunBtn.textContent = "Running";
      metricsOut.textContent = "Running preloaded compressed ONNX CPU and then regular GPU...";
      cpuOut.textContent = "Waiting for compressed ONNX CPU...";
      gpuOut.textContent = "Waiting for regular GPU...";
      diffOut.textContent = "Waiting for compressed ONNX CPU and regular GPU outputs...";
      rawOut.textContent = "Waiting...";
      try {
        const payload = {
          lang: document.getElementById("lang").value,
          trankit_override: document.getElementById("trankitOverride").value,
          manual_sentence_segmentation: document.getElementById("manualSentence").checked,
          strip_punctuation: document.getElementById("stripPunctuation").checked,
          text: document.getElementById("text").value
        };
        const res = await fetch("/api/analyze_onnx_cpu_vs_gpu", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        renderOnnxSummary(data);
        metricsOut.textContent = pretty({
          comparison: data.comparison,
          load: data.load,
          devices: {
            onnx_cpu: data.devices && data.devices.onnx_cpu && data.devices.onnx_cpu.metrics,
            gpu: data.devices && data.devices.gpu && data.devices.gpu.metrics
          }
        });
        cpuOut.textContent = pretty(data.devices && data.devices.onnx_cpu);
        gpuOut.textContent = pretty(data.devices && data.devices.gpu);
        diffOut.textContent = data.discrepancies && data.discrepancies.text ? data.discrepancies.text : "No discrepancy report.";
        rawOut.textContent = pretty(data);
      } catch (err) {
        metricsOut.innerHTML = `<span class="error">${String(err)}</span>`;
      } finally {
        gpuOptRunBtn.disabled = false;
        gpuOptRunBtn.textContent = "Run Compressed ONNX CPU then Regular GPU";
        refreshStatus();
      }
    });

    async function runLoadProbe(mode) {
      const labels = {
        xlm_only: "shared XLM cold-load",
        lang_modules: "selected-language module load",
        full: "full all-language pipeline load"
      };
      const label = labels[mode] || mode;
      const xlmLabel = xlmLoadProbeBtn.textContent;
      const langLabel = langLoadProbeBtn.textContent;
      const fullLabel = fullLoadProbeBtn.textContent;
      showPane("probePane");
      probeSummary.innerHTML = "";
      xlmLoadProbeBtn.disabled = true;
      langLoadProbeBtn.disabled = true;
      fullLoadProbeBtn.disabled = true;
      if (mode === "xlm_only") {
        xlmLoadProbeBtn.textContent = "Loading shared XLM...";
      } else if (mode === "lang_modules") {
        langLoadProbeBtn.textContent = "Loading language modules...";
      } else {
        fullLoadProbeBtn.textContent = "Loading full pipeline...";
      }
      const started = performance.now();
      const updateTimer = () => {
        const elapsed = (performance.now() - started) / 1000;
        probeOut.textContent = `Running ${label} probe: CPU then GPU...\nElapsed: ${fmtSeconds(elapsed)}`;
      };
      updateTimer();
      const timerId = window.setInterval(updateTimer, 250);
      try {
        const res = await fetch("/api/load_probe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode,
            lang: document.getElementById("lang").value,
            warmup_text: document.getElementById("text").value
          })
        });
        const data = await res.json();
        renderLoadProbe(data);
      } catch (err) {
        probeOut.innerHTML = `<span class="error">${String(err)}</span>`;
      } finally {
        window.clearInterval(timerId);
        xlmLoadProbeBtn.disabled = false;
        langLoadProbeBtn.disabled = false;
        fullLoadProbeBtn.disabled = false;
        xlmLoadProbeBtn.textContent = xlmLabel;
        langLoadProbeBtn.textContent = langLabel;
        fullLoadProbeBtn.textContent = fullLabel;
        refreshStatus();
      }
    }

    xlmLoadProbeBtn.addEventListener("click", () => runLoadProbe("xlm_only"));
    langLoadProbeBtn.addEventListener("click", () => runLoadProbe("lang_modules"));
    fullLoadProbeBtn.addEventListener("click", () => runLoadProbe("full"));

    refreshStatus();
    setInterval(refreshStatus, 1500);
