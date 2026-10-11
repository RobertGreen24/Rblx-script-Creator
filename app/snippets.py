"""Built-in Luau snippet catalogue.

These are the copy/paste building blocks shown on /snippets. They are seeded
into SQLite on first run (``builtin = 1``) so users can add their own alongside
them without clashes.
"""

from __future__ import annotations

SNIPPETS: list[dict] = [
    # ------------------------------------------------------------------ Basics
    {
        "title": "Script, LocalScript or ModuleScript?",
        "category": "Basics",
        "summary": "Where each script type runs and what it can touch.",
        "tags": ["architecture", "scripts"],
        "script_type": "module",
        "code": """-- SERVER Script      -> ServerScriptService (or inside a part)
--   Runs once on the server, can touch DataStores, keeps the truth.
--
-- CLIENT LocalScript -> StarterPlayer/StarterPlayerScripts (or StarterGui, tools)
--   Runs in each player's client, owns input and UI. Never trust it.
--
-- MODULE ModuleScript -> ReplicatedStorage or ServerStorage
--   Runs nowhere by itself: server and client each `require` their own copy.
--
-- Handy globals: game, workspace, script, Instance, task, os, math, string, table
print("hello from", script:GetFullName())
""",
    },
    {
        "title": "Server <-> Client remote events",
        "category": "Basics",
        "summary": "The safe pattern for talking between server and client, with validation.",
        "tags": ["remotes", "networking", "security"],
        "script_type": "server",
        "code": """local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")

-- 1. Create the remote once on the server (client uses WaitForChild).
local remote = ReplicatedStorage:FindFirstChild("PurchaseRemote")
if not remote then
	remote = Instance.new("RemoteEvent")
	remote.Name = "PurchaseRemote"
	remote.Parent = ReplicatedStorage
end

-- 2. Always validate: anything from the client can be forged.
local COST = 100
local lastRequest = {}

remote.OnServerEvent:Connect(function(player, itemId, quantity)
	if typeof(itemId) ~= "string" then
		return
	end
	quantity = math.clamp(tonumber(quantity) or 1, 1, 10)

	local now = os.clock()
	if lastRequest[player] and now - lastRequest[player] < 0.25 then
		return  -- rate limit spam clicks
	end
	lastRequest[player] = now

	local leaderstats = player:FindFirstChild("leaderstats")
	local cash = leaderstats and leaderstats:FindFirstChild("Cash")
	if not cash or cash.Value < COST * quantity then
		remote:FireClient(player, "Not enough cash", itemId)
		return
	end

	cash.Value -= COST * quantity
	remote:FireClient(player, "Purchased " .. itemId, itemId)
end)

Players.PlayerRemoving:Connect(function(player)
	lastRequest[player] = nil
end)
""",
    },
    {
        "title": "Wait for a part without errors",
        "category": "Basics",
        "summary": "WaitForChild with a timeout so a missing object cannot hang your script forever.",
        "tags": ["waitforchild", "robustness"],
        "script_type": "module",
        "code": """-- WaitForChild returns nil if it times out -> no silent freeze.
local function waitFor(parent, name, timeout)
	local child = parent:WaitForChild(name, timeout or 5)
	if not child then
		warn(string.format("[%s] '%s' never appeared under %s", script.Name, name, parent:GetFullName()))
	end
	return child
end

local part = waitFor(workspace, "LobbyDoor", 5)
if part then
	print("found", part:GetFullName())
end

-- Type-checked lookup: skip anything that is not the class you expect.
local function findParts(container, className)
	local results = {}
	for _, item in ipairs(container:GetDescendants()) do
		if item:IsA(className) then
			table.insert(results, item)
		end
	end
	return results
end

print(("spawns in the map: %d"):format(#findParts(workspace, "SpawnLocation")))
""",
    },
    # --------------------------------------------------------------- DataStores
    {
        "title": "DataStore with retries",
        "category": "DataStores",
        "summary": "Load/save player data with retry, autosave and BindToClose safety.",
        "tags": ["datastore", "saving", "pcall"],
        "script_type": "server",
        "code": """local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local store = DataStoreService:GetDataStore("PlayerData_v1")
local data = {}

-- In Studio, DataStores only work with "Enable Studio Access to API Services".
local function withRetries(callback, attempts)
	attempts = attempts or 3
	for attempt = 1, attempts do
		local ok, result = pcall(callback)
		if ok then
			return true, result
		end
		warn(("DataStore attempt %d failed: %s"):format(attempt, tostring(result)))
		task.wait(attempt)
	end
	return false
end

local function load(player)
	local ok, saved = withRetries(function()
		return store:GetAsync("u" .. player.UserId)
	end)
	data[player] = (ok and type(saved) == "table") and saved or { cash = 0, wins = 0 }
end

local function save(player)
	if not data[player] or RunService:IsStudio() then
		return
	end
	local snapshot = data[player]
	withRetries(function()
		store:SetAsync("u" .. player.UserId, snapshot)
	end)
end

Players.PlayerAdded:Connect(function(player)
	load(player)
	task.spawn(function()
		while player.Parent and task.wait(120) do
			save(player)
		end
	end)
end)

Players.PlayerRemoving:Connect(function(player)
	save(player)
	data[player] = nil
end)

game:BindToClose(function()
	if RunService:IsStudio() then
		return
	end
	for _, player in ipairs(Players:GetPlayers()) do
		save(player)
	end
	task.wait(3)
end)
""",
    },
    # -------------------------------------------------------------- UI essentials
    {
        "title": "Notification toast",
        "category": "UI",
        "summary": "Slide-in toast message, pure code, no image assets needed.",
        "tags": ["ui", "feedback", "tween"],
        "script_type": "client",
        "code": """local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")

local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.Name = "RF_Toasts"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")

local holder = Instance.new("Frame")
holder.BackgroundTransparency = 1
holder.Position = UDim2.new(1, -20, 1, -20)
holder.AnchorPoint = Vector2.new(1, 1)
holder.Size = UDim2.fromOffset(260, 400)
holder.Parent = gui

local layout = Instance.new("UIListLayout")
layout.VerticalAlignment = Enum.VerticalAlignment.Bottom
layout.HorizontalAlignment = Enum.HorizontalAlignment.Right
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Padding = UDim.new(0, 8)
layout.Parent = holder

local function toast(message, colour)
	local card = Instance.new("TextLabel")
	card.Size = UDim2.fromOffset(250, 44)
	card.BackgroundColor3 = colour or Color3.fromRGB(28, 30, 38)
	card.BackgroundTransparency = 0.08
	card.BorderSizePixel = 0
	card.Font = Enum.Font.GothamMedium
	card.Text = message
	card.TextColor3 = Color3.fromRGB(240, 242, 248)
	card.TextSize = 14
	card.TextWrapped = true
	card.TextXAlignment = Enum.TextXAlignment.Left
	card.Position = UDim2.fromOffset(40, 0)
	card.Parent = holder
	Instance.new("UICorner", card).CornerRadius = UDim.new(0, 10)

	local padding = Instance.new("UIPadding")
	padding.PaddingLeft = UDim.new(0, 12)
	padding.PaddingRight = UDim.new(0, 12)
	padding.Parent = card

	TweenService:Create(card, TweenInfo.new(0.25, Enum.EasingStyle.Quad), { Position = UDim2.fromOffset(0, 0) }):Play()
	task.delay(4, function()
		local out = TweenService:Create(card, TweenInfo.new(0.25), { BackgroundTransparency = 1, TextTransparency = 1 })
		out:Play()
		out.Completed:Wait()
		card:Destroy()
	end)
	return card
end

-- Usage - call toast() from anywhere in this client script:
toast("Welcome back!", Color3.fromRGB(46, 120, 90))

-- Let other scripts fire toasts through a BindableEvent.
local bindable = ReplicatedStorage:FindFirstChild("RF_Toast")
if not bindable then
	bindable = Instance.new("BindableEvent")
	bindable.Name = "RF_Toast"
	bindable.Parent = ReplicatedStorage
end
bindable.Event:Connect(function(message, colour)
	toast(tostring(message), colour)
end)
""",
    },
    {
        "title": "Damage numbers over a player",
        "category": "UI",
        "summary": "BillboardGui that pops a number above the target and fades out.",
        "tags": ["ui", "billboard", "combat"],
        "script_type": "client",
        "code": """local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")

local function popNumber(part, amount, colour)
	local gui = Instance.new("BillboardGui")
	gui.Size = UDim2.fromOffset(80, 34)
	gui.AlwaysOnTop = true
	gui.StudsOffsetWorldSpace = Vector3.new(0, 2.5, 0)
	gui.Parent = part

	local label = Instance.new("TextLabel")
	label.BackgroundTransparency = 1
	label.Size = UDim2.fromScale(1, 1)
	label.Font = Enum.Font.GothamBlack
	label.Text = tostring(amount)
	label.TextColor3 = colour or Color3.fromRGB(255, 92, 92)
	label.TextScaled = true
	label.Parent = gui

	TweenService:Create(gui, TweenInfo.new(0.6, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), {
		StudsOffsetWorldSpace = Vector3.new(0, 6, 0),
	}):Play()

	task.delay(0.45, function()
		local fade = TweenService:Create(label, TweenInfo.new(0.3), { TextTransparency = 1, TextStrokeTransparency = 1 })
		fade:Play()
		fade.Completed:Wait()
		gui:Destroy()
	end)
end

-- Demo: damage numbers whenever the local player takes a hit.
local player = Players.LocalPlayer
local function watch(character)
	local humanoid = character:WaitForChild("Humanoid")
	local root = character:WaitForChild("HumanoidRootPart")
	local previous = humanoid.Health
	humanoid.HealthChanged:Connect(function(current)
		local delta = previous - current
		previous = current
		if delta > 0 then
			popNumber(root, math.floor(delta + 0.5))
		end
	end)
end

if player.Character then
	watch(player.Character)
end
player.CharacterAdded:Connect(watch)
""",
    },
    {
        "title": "Sound effect helper",
        "category": "UI",
        "summary": "Spawn a sound on a part, play it, clean it up.",
        "tags": ["sound", "audio"],
        "script_type": "module",
        "code": """local SoundService = game:GetService("SoundService")

local Sfx = {}

-- Roblox ships a few free sounds under rbxasset:// - swap in your own IDs.
Sfx.Library = {
	click = "rbxasset://sounds/electronicpingshort.wav",
	impact = "rbxasset://sounds/impact_water.mp3",
	coin = "rbxasset://sounds/switch3.wav",
	victory = "rbxasset://sounds/victory.wav",
}

function Sfx.play(soundId, parent, volume)
	local sound = Instance.new("Sound")
	sound.SoundId = Sfx.Library[soundId] or soundId
	sound.Volume = volume or 1
	sound.RollOffMaxDistance = 80
	sound.Parent = parent or SoundService
	sound:Play()
	sound.Ended:Connect(function()
		sound:Destroy()
	end)
	return sound
end

return Sfx
""",
    },
    # ------------------------------------------------------------------- Combat
    {
        "title": "Melee tool that actually damages",
        "category": "Combat",
        "summary": "Tool with a swing cooldown, range check and server-side damage.",
        "tags": ["combat", "tool", "server"],
        "script_type": "server",
        "code": """local Players = game:GetService("Players")
local Debris = game:GetService("Debris")

local tool = script.Parent          -- this script lives INSIDE the Tool
local DAMAGE = 20
local RANGE = 7
local COOLDOWN = 0.6

local lastSwing = {}

local function hitOnce(humanoid, damage)
	if humanoid.Health <= 0 then
		return
	end
	humanoid:TakeDamage(damage)
end

tool.Activated:Connect(function()
	local character = tool.Parent
	local player = Players:GetPlayerFromCharacter(character)
	if not player or not character then
		return
	end

	local now = os.clock()
	if lastSwing[player] and now - lastSwing[player] < COOLDOWN then
		return
	end
	lastSwing[player] = now

	local root = character:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end

	-- Optional slash VFX so the swing is visible.
	local slash = Instance.new("Part")
	slash.Size = Vector3.new(4, 0.2, 6)
	slash.CanCollide = false
	slash.Anchored = true
	slash.CFrame = root.CFrame * CFrame.new(0, 0, -3)
	slash.Transparency = 0.5
	slash.Color = Color3.new(1, 1, 1)
	slash.Parent = workspace
	Debris:AddItem(slash, 0.15)

	local hitSomeone = false
	for _, other in ipairs(Players:GetPlayers()) do
		if other ~= player and other.Character then
			local otherRoot = other.Character:FindFirstChild("HumanoidRootPart")
			local otherHumanoid = other.Character:FindFirstChildOfClass("Humanoid")
			if otherRoot and otherHumanoid then
				if (otherRoot.Position - root.Position).Magnitude <= RANGE and otherHumanoid.Health > 0 then
					hitOnce(otherHumanoid, DAMAGE)
					hitSomeone = true
				end
			end
		end
	end

	if hitSomeone then
		local impact = Instance.new("Sound")
		impact.SoundId = "rbxasset://sounds/impact_water.mp3"
		impact.Volume = 0.6
		impact.Parent = root
		impact:Play()
		Debris:AddItem(impact, 3)
	end
end)

Players.PlayerRemoving:Connect(function(player)
	lastSwing[player] = nil
end)
""",
    },
    # --------------------------------------------------------------- Animation
    {
        "title": "Play an animation on the character",
        "category": "Animation",
        "summary": "Load an Animation onto the humanoid and play it safely.",
        "tags": ["animation", "humanoid"],
        "script_type": "client",
        "code": """local Players = game:GetService("Players")

local player = Players.LocalPlayer
local ANIMATION_ID = "rbxassetid://507771019"  -- replace with your own asset

local function bind(character)
	local humanoid = character:WaitForChild("Humanoid")
	local animator = humanoid:FindFirstChildOfClass("Animator") or Instance.new("Animator", humanoid)

	local animation = Instance.new("Animation")
	animation.AnimationId = ANIMATION_ID

	local track = animator:LoadAnimation(animation)

	local function playOnce()
		if track.IsPlaying then
			return
		end
		track:Play(0.1, 1, 1.2)  -- fadeIn, weight, speed
	end

	-- Play on a key press, on spawn, or from your UI.
	local UserInputService = game:GetService("UserInputService")
	UserInputService.InputBegan:Connect(function(input, processed)
		if not processed and input.KeyCode == Enum.KeyCode.G then
			playOnce()
		end
	end)
end

if player.Character then
	bind(player.Character)
end
player.CharacterAdded:Connect(bind)
""",
    },
    # ---------------------------------------------------------------- Game loops
    {
        "title": "Timer + countdown text",
        "category": "Game loops",
        "summary": "Countdown that drives a label, a colour change and a callback.",
        "tags": ["timer", "ui", "loop"],
        "script_type": "client",
        "code": """local RunService = game:GetService("RunService")

local function startCountdown(seconds, label, onFinished)
	local remaining = seconds
	local connection
	connection = RunService.RenderStepped:Connect(function(deltaTime)
		remaining = math.max(0, remaining - deltaTime)
		local whole = math.ceil(remaining)

		if label then
			label.Text = string.format("%d:%02d", math.floor(whole / 60), whole % 60)
			-- Red when time is nearly up, green once there is plenty left.
			local t = remaining / seconds
			label.TextColor3 = Color3.fromRGB(255, 96, 96):Lerp(Color3.fromRGB(120, 230, 150), t)
		end

		if remaining <= 0 then
			connection:Disconnect()
			if onFinished then
				onFinished()
			end
		end
	end)
	return connection
end

-- Example: a 30 second round timer that prints when it ends.
local label = Instance.new("TextLabel")
label.Size = UDim2.fromOffset(160, 50)
label.Position = UDim2.new(0.5, -80, 0, 20)
label.BackgroundColor3 = Color3.fromRGB(24, 26, 33)
label.TextColor3 = Color3.fromRGB(245, 245, 250)
label.TextScaled = true
label.Font = Enum.Font.GothamBold
label.Parent = game:GetService("Players").LocalPlayer:WaitForChild("PlayerGui")
Instance.new("UICorner", label).CornerRadius = UDim.new(0, 10)

startCountdown(30, label, function()
	print("Time up!")
	label.Text = "GO!"
end)
""",
    },
    # ----------------------------------------------------------------- Utilities
    {
        "title": "Useful helper functions",
        "category": "Utilities",
        "summary": "Number formatting, shuffle, weighted chance and a safe getter.",
        "tags": ["helpers", "table", "math"],
        "script_type": "module",
        "code": """local Helpers = {}

-- 1234567 -> "1.23M"
function Helpers.formatShortNumber(value)
	value = tonumber(value) or 0
	for _, unit in ipairs({ { 1e12, "T" }, { 1e9, "B" }, { 1e6, "M" }, { 1e3, "K" } }) do
		if value >= unit[1] then
			return string.format("%.2f%s", value / unit[1], unit[2])
		end
	end
	return tostring(math.floor(value))
end

-- Fisher-Yates shuffle (do not trust sort(..., function() return math.random() end)).
function Helpers.shuffle(list)
	for index = #list, 2, -1 do
		local swap = math.random(index)
		list[index], list[swap] = list[swap], list[index]
	end
	return list
end

-- Weighted pick: Helpers.weighted({ common = 80, rare = 18, epic = 2 })
function Helpers.weighted(weights)
	local total = 0
	for _, weight in pairs(weights) do
		total += weight
	end
	local roll = math.random() * total
	for key, weight in pairs(weights) do
		roll -= weight
		if roll <= 0 then
			return key
		end
	end
	return nil
end

-- Deep-ish read: Helpers.get(data, "inventory", "sword", "level")
function Helpers.get(root, ...)
	local current = root
	for _, key in ipairs({ ... }) do
		if type(current) ~= "table" then
			return nil
		end
		current = current[key]
	end
	return current
end

function Helpers.round(value, decimals)
	local factor = 10 ^ (decimals or 0)
	return math.floor(value * factor + 0.5) / factor
end

return Helpers
""",
    },
    {
        "title": "Debugging: measure and warn",
        "category": "Utilities",
        "summary": "Time a block of code and see exactly where your microseconds go.",
        "tags": ["debug", "performance", "profiling"],
        "script_type": "module",
        "code": """--[[
	Wrap a block in time() to see how long it really takes.
	Keep it around while tuning; delete it before shipping if you like.
--]]
local function time(label, callback)
	local started = os.clock()
	local result = callback()
	print(string.format("[time] %-28s %6.2f ms", label, (os.clock() - started) * 1000))
	return result
end

local map = workspace

local parts = time("collect parts", function()
	local found = {}
	for _, item in ipairs(map:GetDescendants()) do
		if item:IsA("BasePart") then
			table.insert(found, item)
		end
	end
	return found
end)

-- MicroProfiler: press Ctrl+F6 in Studio (or F6 then Ctrl+F6) to record a frame.
-- Also handy: debug.profilebegin("tag") / debug.profileend() around hot code.
print(("collected %d parts"):format(#parts))

-- Handy for reading a value that might not exist yet:
local function safe(fn, fallback)
	local ok, value = pcall(fn)
	return ok and value ~= nil and value or fallback
end

print("player count:", safe(function()
	return #game:GetService("Players"):GetPlayers()
end, 0))
""",
    },
]
