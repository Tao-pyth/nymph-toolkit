// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir } from "node:fs/promises";
import { createInterface } from "node:readline";
import { chromium } from "playwright";

const args = process.argv.slice(2);
const browser = await chromium.launch({executablePath:process.env.NTK_DIAGNOSTICS_BROWSER || undefined});
try {
  if (args[0] === "--tabs") {
    const count = Number(args[1]);
    if (![1, 3].includes(count) || args.length !== 6) throw new Error("Expected tab count and four Runtime URLs");
    const pages = await Promise.all(args.slice(2).flatMap((url) =>
      Array.from({length:count}, async () => {
        const page = await browser.newPage();
        await page.goto(url);
        await page.waitForFunction(() => document.getElementById("runtime").textContent === "稼働中");
        return page;
      })));
    assert.equal(pages.length, count * 4);
    process.stdout.write("ready\n");
    process.stdin.resume();
    await once(process.stdin, "end");
  } else {
    const child = spawn(args[0] || "python", ["examples/runtime_diagnostics_demo.py", "--seconds", "16"],
                        {stdio:["ignore", "pipe", "inherit"]});
    const done = once(child, "exit");
    const lines = createInterface({input:child.stdout});
    const line = await Promise.race([once(lines,"line"), done]);
    assert.match(String(line[0]), /^http:\/\/127\.0\.0\.1:\d+\/$/);
    try {
      const page = await browser.newPage({viewport:{width:390,height:820}});
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      let invocations = 0;
      page.on("request", (request) => {
        if (request.url().endsWith("/api/console")) invocations++;
      });
      await page.goto(line[0]);
      await page.getByText("天気情報", {exact:true}).waitFor();
      assert.equal(await page.locator("#adapter option").count(), 1);
      assert.ok(await page.getByText("地域 東京").isVisible());
      const action = page.getByRole("button", {name:"天気サンプルの状態を照会"});
      await action.focus();
      await page.keyboard.press("Enter");
      await page.waitForFunction(() => document.querySelector("#result").textContent.includes('"observations": 1'));
      assert.equal(invocations, 1);
      assert.ok(!(await page.locator("#result").textContent()).includes("provider"));
      await page.locator("#event-filter").focus();
      await page.keyboard.press("ArrowDown");
      assert.equal(await page.locator("#event-filter").inputValue(), "activity");
      await page.reload();
      await page.getByText("天気情報", {exact:true}).waitFor();
      assert.equal(invocations, 1);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
      await mkdir("output/diagnostics", {recursive:true});
      await page.screenshot({path:"output/diagnostics/mobile.png", fullPage:true});
      await page.setViewportSize({width:1280,height:900});
      await page.screenshot({path:"output/diagnostics/desktop.png", fullPage:true});
      await page.clock.setFixedTime(new Date(Date.now() + 45_000));
      await page.getByText("期限切れ", {exact:true}).waitFor();
      assert.deepEqual(errors, []);
      console.log("PASS: local browser, keyboard, status query, no reload side effect, expiry, mobile");
    } finally {
      const [exitCode] = await done;
      assert.equal(exitCode, 0);
    }
  }
} finally {
  await browser.close();
}
