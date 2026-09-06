-- fork.lua — the nvim side of slash-fork (spec R11, D11, D24).
--
-- Loaded via: nvim --cmd "luafile fork.lua"   (the kitten launches this in a
-- fresh kitty OS window of class hk-fork, with HK_FORK_PANE + HK_FORK_ASSETS
-- in the env — launched windows inherit no HERDR_* env, census-map P69).
--
-- Contract (spec D11):
--   * BufWritePost and VimLeavePre are the ONLY delivery decision points;
--   * first :w delivers the whole buffer via `hk send` (bracketed, populate-only);
--   * an append-only save delivers only the appended suffix;
--   * a save editing inside delivered text delivers nothing + a notification;
--   * :q! or crash delivers nothing (VimLeavePre with a modified buffer is a no-op);
--   * --submit (HK_FORK_SUBMIT=1) routes through agent prompt (spec 11.6);
--   * the target pane is NEVER read (spec F.8) — the buffer starts blank.
--
-- The delivery-state decision lives in kitten/fork_state.py (pure python,
-- unit-tested); this file only collects the buffer and shells out.

local pane = os.getenv("HK_FORK_PANE")
if pane == nil or pane == "" then
  return -- not a fork window; nothing to do (spec 11.8)
end

-- Locating fork_state.py (BUG-4). The candidates below are the two trees that
-- actually exist, plus the flat one for safety; before round2-02 neither
-- candidate matched an installed tree, so an installed fork window found no
-- helper and delivered nothing, silently.
--
--   installed  HK_FORK_ASSETS=<kitty config>/hk/assets -> ../fork_state.py
--   dev / nix  HK_FORK_ASSETS=<repo>/assets            -> ../kitten/fork_state.py
--
-- tests/smoke/g18-install-layout.sh reads these very lines out of this file and
-- asserts one of them resolves against a freshly installed tree.
local assets = os.getenv("HK_FORK_ASSETS") or ""
local helper = nil
for _, cand in ipairs({
  assets .. "/../fork_state.py",
  assets .. "/../kitten/fork_state.py",
  assets .. "/fork_state.py",
}) do
  if vim.fn.filereadable(cand) == 1 then
    helper = cand
    break
  end
end
if helper == nil then
  vim.notify("hk fork: fork_state.py not found under " .. assets ..
    "/.. — reinstall with install.sh", vim.log.levels.ERROR)
  return
end
local state = vim.fn.tempname() .. ".hk-fork-state"
local submit = os.getenv("HK_FORK_SUBMIT") == "1"

-- open a scratch file so :w works on the blank buffer
local scratch = vim.fn.tempname() .. ".hk-fork.md"
vim.cmd("edit " .. vim.fn.fnameescape(scratch))

local function deliver()
  local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  local content = table.concat(lines, "\n")
  if #lines > 0 and content ~= "" then
    content = content .. "\n"
  end
  local cmd = { "python3", helper, "--state", state, "--pane", pane }
  if submit then
    table.insert(cmd, "--submit")
  end
  local result = vim.system(cmd, { stdin = content }):wait()
  if result.code == 65 then
    vim.notify("hk fork: edit inside delivered text; nothing delivered", vim.log.levels.WARN)
  elseif result.code ~= 0 then
    vim.notify("hk fork: delivery failed (" .. tostring(result.code) .. ")", vim.log.levels.ERROR)
  end
end

local group = vim.api.nvim_create_augroup("HkFork", { clear = true })
vim.api.nvim_create_autocmd("BufWritePost", { group = group, callback = deliver })
vim.api.nvim_create_autocmd("VimLeavePre", {
  group = group,
  callback = function()
    -- :q on a saved buffer: everything already went out via BufWritePost.
    -- :q! / crash: buffer modified -> deliver nothing (spec 11.5).
    if not vim.bo.modified then
      return
    end
  end,
})
