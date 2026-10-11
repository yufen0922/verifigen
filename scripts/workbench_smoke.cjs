/* Optional browser acceptance test; install playwright before running. */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHANNEL
      ? { channel: process.env.PLAYWRIGHT_CHANNEL }
      : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1080 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  try {
    await page.goto(process.env.WORKBENCH_URL || "http://127.0.0.1:8765");
    await page.waitForFunction(
      () => document.querySelector("#preset").options.length === 6,
    );
    assert.equal(
      await page.locator("#model-label").textContent(),
      "qwen3.5-flash",
    );
    assert.ok((await page.locator("svg.lucide").count()) > 0);
    fs.mkdirSync("runs/screenshots", { recursive: true });
    await page.screenshot({
      path: "runs/screenshots/workbench-desktop.png",
      fullPage: true,
    });
    for (const viewport of [
      { width: 390, height: 844 },
      { width: 768, height: 1024 },
    ]) {
      await page.setViewportSize(viewport);
      await page.waitForTimeout(300);
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
      await page.screenshot({
        path: `runs/screenshots/workbench-${viewport.width}.png`,
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 1440, height: 1080 });
    await page.locator("#source").fill("{");
    await page.locator("#run").click();
    assert.match(await page.locator("#notice").textContent(), /有效 JSON/);
    await page.locator("#reset").click();
    if (process.argv.includes("--live")) {
      await page.locator("#run").click();
      await page.waitForFunction(
        () =>
          ["passed", "fallback"].some((s) =>
            document.querySelector("#run-state").classList.contains(s),
          ),
        null,
        { timeout: 180000 },
      );
      await page.waitForFunction(
        () => !document.querySelector("#export").disabled,
      );
      assert.ok((await page.locator(".round").count()) > 0);
      assert.ok(Number(await page.locator("#call-count").textContent()) > 0);
      await page.screenshot({
        path: "runs/screenshots/workbench-live.png",
        fullPage: true,
      });
      console.log(
        "Live result:",
        await page.locator("#run-state").textContent(),
        await page.locator("#reason").textContent(),
      );
    }
    await page.locator('[data-view="history"]').click();
    await page.waitForFunction(
      () => document.querySelector("#history-rows").children.length > 0,
    );
    await page.locator('[data-view="evaluation"]').click();
    await page.waitForFunction(
      () => document.querySelector("#evaluation-rows").children.length >= 180,
    );
    await page.locator("#evaluation-rows button").first().click();
    assert.equal(
      await page.locator("#record-dialog").evaluate((el) => el.open),
      true,
    );
    await page.locator("#close-dialog").click();
    if (
      await page.locator('#evaluation-select option[value="ragtruth"]').count()
    ) {
      await page.locator("#evaluation-select").selectOption("ragtruth");
      assert.equal(await page.locator("#evaluation-rows tr").count(), 420);
      assert.match(
        await page.locator("#evaluation-metrics").textContent(),
        /78.57%/,
      );
      await page.locator("#evaluation-filter").selectOption("wrong");
      assert.equal(await page.locator("#evaluation-rows tr").count(), 90);
      await page.locator("#evaluation-filter").selectOption("release");
      assert.match(
        await page.locator("#evaluation-rows").textContent(),
        /独立评审尚未完成/,
      );
      await page.locator("#evaluation-filter").selectOption("all");
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(300);
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
      await page.screenshot({
        path: "runs/screenshots/evaluation-mobile.png",
        fullPage: false,
      });
    }
    await page.locator('[data-view="baselines"]').click();
    await page.waitForFunction(
      () => document.querySelector("#baseline-metrics").children.length === 4,
    );
    assert.equal(await page.locator("#baseline-records tr").count(), 60);
    assert.match(await page.locator("#baseline-note").textContent(), /68.33%/);
    await page.locator("#baseline-arm").selectOption("self_refine");
    assert.equal(await page.locator("#baseline-records tr").count(), 60);
    await page.locator("#baseline-records button").first().click();
    assert.match(await page.locator("#record-content").textContent(), /cross_model_automatic_proxy/);
    await page.locator("#close-dialog").click();
    for (const viewport of [
      { width: 1440, height: 1080 },
      { width: 390, height: 844 },
      { width: 320, height: 700 },
    ]) {
      await page.setViewportSize(viewport);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.screenshot({path: `runs/screenshots/baselines-${viewport.width}.png`, fullPage: false});
    }
    await page.setViewportSize({ width: 1440, height: 1080 });
    const ownRun = await page.request.post(
      `${process.env.WORKBENCH_URL || "http://127.0.0.1:8765"}/api/runs`,
      {data: {scenario: "custom", source: {}, prompt: "Browser deletion check",
        criteria: [{id: "grounding", description: "Do not invent facts"}],
        output_schema: {type: "object"}, initial: {}, max_model_calls: 0}},
    );
    assert.equal(ownRun.status(), 202);
    const ownId = (await ownRun.json()).id;
    await page.request.get(`${process.env.WORKBENCH_URL || "http://127.0.0.1:8765"}/api/runs/${ownId}/events`);
    await page.locator('[data-view="history"]').click();
    const ownRow = page.locator(`#history-rows tr[data-run-id="${ownId}"]`);
    await ownRow.waitFor();
    page.once("dialog", (dialog) => dialog.accept());
    await ownRow.locator('[aria-label="删除本地运行记录"]').click();
    await page.waitForTimeout(300);
    assert.equal((await page.request.get(`${process.env.WORKBENCH_URL || "http://127.0.0.1:8765"}/api/runs/${ownId}`)).status(), 404);
    assert.deepEqual(errors, []);
    console.log(
      "Workbench browser acceptance passed at desktop, tablet and mobile widths.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
