"""The RobloxForge feature catalogue.

Every feature knows how to turn a small set of typed parameters into one or
more complete, production-shaped Luau scripts (server / client / module).

The Luau lives in module-level templates so it stays readable and reviewable,
and every placeholder is filled through :class:`string.Template` - Luau code
contains ``{`` and ``}`` (tables) so ``str.format`` would be a poor fit.
"""

from __future__ import annotations

import re
from string import Template

from .core import (
    Feature,
    Param,
    Script,
    header,
    lint,
    lua_bool,
    lua_list,
    num,
    q,
    slugify,
)

CATEGORIES = ("Movement", "Player Stats", "World & Hazards", "Game Systems")

STATS_USERS = {"leaderstats", "coin_collect", "income"}


def _fill(template: str, values: dict) -> str:
    """Substitute placeholders and tidy the generated file."""
    rendered = Template(template).substitute(values).lstrip("\n")
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered.rstrip() + "\n"


# --------------------------------------------------------------------------- #
#  Shared library snippets
# --------------------------------------------------------------------------- #

TAG_HELPER = r"""
local function watchTagged(tagName, onPartReady)
	local hooked = setmetatable({}, { __mode = "k" })

	local function hook(part)
		if hooked[part] or not part:IsA("BasePart") then
			return
		end
		hooked[part] = true
		onPartReady(part)
	end

	local function consider(instance)
		if instance:IsA("BasePart") and (instance.Name == tagName or CollectionService:HasTag(instance, tagName)) then
			hook(instance)
		end
	end

	for _, instance in ipairs(workspace:GetDescendants()) do
		consider(instance)
	end
	workspace.DescendantAdded:Connect(consider)
	CollectionService:GetInstanceAddedSignal(tagName):Connect(hook)
end
"""

TOUCH_HELPER = r"""
-- Fires `callback(character, humanoid)` at most once every cooldown seconds,
-- so a single physics step cannot trigger a part five times.
local function onTouchDebounced(part, cooldown, callback)
	local lastTouch = {}
	part.Touched:Connect(function(hit)
		local character = hit:FindFirstAncestorOfClass("Model")
		if not character then
			return
		end
		local player = Players:GetPlayerFromCharacter(character)
		if not player then
			return
		end
		local now = os.clock()
		if lastTouch[player] and now - lastTouch[player] < cooldown then
			return
		end
		lastTouch[player] = now
		local humanoid = character:FindFirstChildOfClass("Humanoid")
		if humanoid then
			callback(character, humanoid, player)
		end
	end)
end
"""


# --------------------------------------------------------------------------- #
#  Movement
# --------------------------------------------------------------------------- #

SPRINT = r"""
${header}local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")

local WALK_SPEED = ${walk}
local SPRINT_SPEED = ${sprint}
local SPRINT_KEY = Enum.KeyCode.${key}
local STAMINA_ENABLED = ${stamina}
local MAX_STAMINA = ${max_stamina}
local STAMINA_PER_SECOND = ${stamina_rate}

local player = Players.LocalPlayer
local humanoid = nil
local sprinting = false
local stamina = MAX_STAMINA

local function applySpeed()
	if not humanoid then
		return
	end
	if sprinting and (not STAMINA_ENABLED or stamina > 0) then
		humanoid.WalkSpeed = SPRINT_SPEED
	else
		humanoid.WalkSpeed = WALK_SPEED
	end
end

local function setSprinting(state)
	sprinting = state and (not STAMINA_ENABLED or stamina > 0)
	applySpeed()
end

local function bindCharacter(character)
	humanoid = character:WaitForChild("Humanoid")
	stamina = MAX_STAMINA
	humanoid.WalkSpeed = WALK_SPEED
	humanoid.Died:Connect(function()
		setSprinting(false)
	end)
	applySpeed()
end

if player.Character then
	bindCharacter(player.Character)
end
player.CharacterAdded:Connect(bindCharacter)

UserInputService.InputBegan:Connect(function(input, processed)
	if processed or input.KeyCode ~= SPRINT_KEY then
		return
	end
	setSprinting(true)
end)

UserInputService.InputEnded:Connect(function(input)
	if input.KeyCode == SPRINT_KEY then
		setSprinting(false)
	end
end)

${stamina_loop}"""

SPRINT_STAMINA_LOOP = r"""-- Burn / regrow stamina on the client and keep the speed in sync.
task.spawn(function()
	while true do
		local dt = task.wait(0.1)
		if not STAMINA_ENABLED then
			continue
		end
		if sprinting then
			stamina = math.max(0, stamina - STAMINA_PER_SECOND * dt)
			if stamina <= 0 then
				sprinting = false
			end
		else
			stamina = math.min(MAX_STAMINA, stamina + (STAMINA_PER_SECOND * 0.75) * dt)
		end
		applySpeed()
	end
end)
"""

DOUBLE_JUMP = r"""
${header}local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")

local MAX_JUMPS = ${max_jumps}
local JUMP_POWER = ${jump_power}
local ALLOW_TOUCH_BUTTON = ${mobile}

local player = Players.LocalPlayer
local jumpsUsed = 0
local humanoid = nil

local function bindCharacter(character)
	humanoid = character:WaitForChild("Humanoid")
	jumpsUsed = 0

	humanoid.StateChanged:Connect(function(_, newState)
		if newState == Enum.HumanoidStateType.Landed then
			jumpsUsed = 0
		elseif newState == Enum.HumanoidStateType.Swimming then
			jumpsUsed = 0
		end
	end)
end

if player.Character then
	bindCharacter(player.Character)
end
player.CharacterAdded:Connect(bindCharacter)

local function tryExtraJump()
	if not humanoid or humanoid.Health <= 0 then
		return
	end
	if humanoid:GetState() ~= Enum.HumanoidStateType.Freefall then
		return
	end
	if jumpsUsed >= MAX_JUMPS - 1 then
		return
	end

	jumpsUsed += 1
	local root = humanoid.RootPart
	if root then
		-- Small upward nudge keeps the extra jump feeling crisp.
		local velocity = root.AssemblyLinearVelocity
		root.AssemblyLinearVelocity = Vector3.new(velocity.X, math.max(velocity.Y, JUMP_POWER * 0.35), velocity.Z)
	end
	humanoid:ChangeState(Enum.HumanoidStateType.Jumping)
end

UserInputService.JumpRequest:Connect(tryExtraJump)

${mobile_block}"""

DOUBLE_JUMP_MOBILE = r"""if ALLOW_TOUCH_BUTTON then
	-- Mobile players have no space bar - give them a button instead.
	local playerGui = player:WaitForChild("PlayerGui")
	local gui = Instance.new("ScreenGui")
	gui.Name = "RF_DoubleJump"
	gui.ResetOnSpawn = false
	gui.Parent = playerGui

	local button = Instance.new("TextButton")
	button.Size = UDim2.fromOffset(70, 70)
	button.Position = UDim2.new(1, -90, 1, -170)
	button.BackgroundColor3 = Color3.fromRGB(32, 36, 46)
	button.BackgroundTransparency = 0.25
	button.Text = "JUMP"
	button.TextColor3 = Color3.fromRGB(240, 240, 245)
	button.TextScaled = true
	button.Font = Enum.Font.GothamBold
	button.AutoButtonColor = true
	button.Parent = gui
	Instance.new("UICorner").Parent = button

	button.MouseButton1Click:Connect(tryExtraJump)
end
"""

DASH = r"""
${header}local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")

local DASH_KEY = Enum.KeyCode.${key}
local DASH_SPEED = ${speed}
local DASH_TIME = ${time}
local COOLDOWN = ${cooldown}
local ALLOW_IN_AIR = ${allow_air}

local player = Players.LocalPlayer
local lastDash = 0
local dashing = false

local function dash()
	if dashing or os.clock() - lastDash < COOLDOWN then
		return
	end
	local character = player.Character
	if not character then
		return
	end
	local humanoid = character:FindFirstChildOfClass("Humanoid")
	local root = character:FindFirstChild("HumanoidRootPart")
	if not humanoid or not root or humanoid.Health <= 0 then
		return
	end
	if not ALLOW_IN_AIR and humanoid:GetState() == Enum.HumanoidStateType.Freefall then
		return
	end

	lastDash = os.clock()
	dashing = true

	-- Direction: where the player is holding the stick, else the camera's forward.
	local direction = humanoid.MoveDirection
	if direction.Magnitude < 0.1 then
		local camera = workspace.CurrentCamera
		direction = camera and camera.CFrame.LookVector or root.CFrame.LookVector
	end
	direction = Vector3.new(direction.X, 0, direction.Z)
	if direction.Magnitude < 0.1 then
		direction = root.CFrame.LookVector
	end
	direction = direction.Unit

	local attachment = Instance.new("Attachment")
	attachment.Parent = root

	local force = Instance.new("LinearVelocity")
	force.Attachment0 = attachment
	force.RelativeTo = Enum.ActuatorRelativeTo.World
	force.VelocityConstraintMode = Enum.VelocityConstraintMode.Vector
	force.MaxForce = math.huge
	force.VectorVelocity = direction * DASH_SPEED
	force.Parent = root

	task.delay(DASH_TIME, function()
		force:Destroy()
		attachment:Destroy()
		dashing = false
	end)
end

UserInputService.InputBegan:Connect(function(input, processed)
	if processed then
		return
	end
	if input.KeyCode == DASH_KEY then
		dash()
	elseif input.KeyCode == Enum.KeyCode.ButtonL1 then
		dash()
	end
end)
"""


# --------------------------------------------------------------------------- #
#  Player stats
# --------------------------------------------------------------------------- #

COIN_COLLECT = r"""
${header}local Players = game:GetService("Players")
local CollectionService = game:GetService("CollectionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")

local StatsAPI = require(ReplicatedStorage.Shared.StatsAPI)

local TAG = "${tag}"
local AWARD_STAT = "${stat}"
local AWARD_AMOUNT = ${amount}
local RESPAWN_SECONDS = ${respawn}
local SPIN = ${spin}
local FLOAT_HEIGHT = ${float}

${tag_helper}local busy = setmetatable({}, { __mode = "k" })

local function startEffects(coin)
	if SPIN > 0 then
		local spin = TweenService:Create(
			coin,
			TweenInfo.new(360 / SPIN, Enum.EasingStyle.Linear, Enum.EasingDirection.Out, -1),
			{ CFrame = coin.CFrame * CFrame.Angles(0, math.rad(360), 0) }
		)
		spin:Play()
	end
	if FLOAT_HEIGHT > 0 then
		local base = coin.Position.Y
		task.spawn(function()
			while coin.Parent do
				local t = os.clock() * 2
				coin.Position = Vector3.new(coin.Position.X, base + math.sin(t) * FLOAT_HEIGHT, coin.Position.Z)
				task.wait(0.03)
			end
		end)
	end
end

local function respawn(coin)
	task.wait(RESPAWN_SECONDS)
	if not coin.Parent then
		return
	end
	coin.Transparency = 0
	coin.CanTouch = true
	coin.CanCollide = false
	busy[coin] = nil
end

local function onTouch(coin, hit)
	if busy[coin] then
		return
	end
	local character = hit:FindFirstAncestorOfClass("Model")
	local player = character and Players:GetPlayerFromCharacter(character)
	if not player then
		return
	end

	busy[coin] = true
	StatsAPI.add(player, AWARD_STAT, AWARD_AMOUNT)

	-- Quick "collected" feedback before hiding the coin.
	coin.CanTouch = false
	coin.Transparency = 1
	task.spawn(respawn, coin)
end

watchTagged(TAG, function(coin)
	coin.Anchored = true
	coin.CanCollide = false
	coin.CanTouch = true
	coin.Touched:Connect(function(hit)
		onTouch(coin, hit)
	end)
	startEffects(coin)
end)

print(string.format("[Coins] watching %d coin(s) tagged/name '%s'", #CollectionService:GetTagged(TAG), TAG))
"""

INCOME = r"""
${header}local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local StatsAPI = require(ReplicatedStorage.Shared.StatsAPI)

local PAY_STAT = "${stat}"
local PAY_AMOUNT = ${amount}
local INTERVAL = ${interval}
local OFFLINE_CAP = ${cap}

-- Give AFK players something for hanging around: a flat wage, or a wage that
-- grows with how long they have been in the server.
local function award(player)
	local seconds = player:GetAttribute("RF_SessionSeconds") or 0
	local multiplier = ${growth} and (1 + math.floor(seconds / 60)) or 1
	local payout = math.min(PAY_AMOUNT * multiplier, OFFLINE_CAP)
	StatsAPI.add(player, PAY_STAT, payout)
end

local function track(player)
	player:SetAttribute("RF_SessionSeconds", 0)
	task.spawn(function()
		while player.Parent do
			task.wait(1)
			player:SetAttribute("RF_SessionSeconds", (player:GetAttribute("RF_SessionSeconds") or 0) + 1)
		end
	end)
end

Players.PlayerAdded:Connect(track)
for _, player in ipairs(Players:GetPlayers()) do
	track(player)
end

task.spawn(function()
	while true do
		task.wait(INTERVAL)
		for _, player in ipairs(Players:GetPlayers()) do
			award(player)
		end
	end
end)
"""

LEADERBOARD_GUI = r"""
${header}local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local STAT = "${stat}"
local ROW_COUNT = ${rows}
local REFRESH = ${refresh}
local SHOW_SELF = ${self}

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

local gui = Instance.new("ScreenGui")
gui.Name = "RF_Leaderboard"
gui.ResetOnSpawn = false
gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
gui.Parent = playerGui

local frame = Instance.new("Frame")
frame.Name = "Board"
frame.AnchorPoint = Vector2.new(1, 0)
frame.Position = UDim2.new(1, -18, 0, 18)
frame.Size = UDim2.fromOffset(230, 44 + ROW_COUNT * 26)
frame.BackgroundColor3 = Color3.fromRGB(22, 24, 31)
frame.BackgroundTransparency = 0.1
frame.BorderSizePixel = 0
frame.Parent = gui
Instance.new("UICorner", frame).CornerRadius = UDim.new(0, 10)

local stroke = Instance.new("UIStroke")
stroke.Color = Color3.fromRGB(255, 255, 255)
stroke.Transparency = 0.88
stroke.Thickness = 1
stroke.Parent = frame

local padding = Instance.new("UIPadding")
padding.PaddingTop = UDim.new(0, 10)
padding.PaddingLeft = UDim.new(0, 12)
padding.PaddingRight = UDim.new(0, 12)
padding.Parent = frame

local title = Instance.new("TextLabel")
title.Name = "Title"
title.Size = UDim2.new(1, 0, 0, 22)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBold
title.Text = "${title}"
title.TextColor3 = Color3.fromRGB(245, 246, 250)
title.TextSize = 15
title.TextXAlignment = Enum.TextXAlignment.Left
title.Parent = frame

local layout = Instance.new("UIListLayout")
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Padding = UDim.new(0, 4)
layout.Parent = frame

local rows = {}
for index = 1, ROW_COUNT do
	local row = Instance.new("Frame")
	row.Name = "Row" .. index
	row.LayoutOrder = index
	row.Size = UDim2.new(1, 0, 0, 22)
	row.BackgroundTransparency = 1
	row.Parent = frame

	local rank = Instance.new("TextLabel")
	rank.Name = "Rank"
	rank.Size = UDim2.new(0, 20, 1, 0)
	rank.BackgroundTransparency = 1
	rank.Font = Enum.Font.GothamMedium
	rank.Text = "#" .. index
	rank.TextColor3 = Color3.fromRGB(150, 156, 172)
	rank.TextSize = 13
	rank.TextXAlignment = Enum.TextXAlignment.Left
	rank.Parent = row

	local name = Instance.new("TextLabel")
	name.Name = "PlayerName"
	name.Position = UDim2.new(0, 24, 0, 0)
	name.Size = UDim2.new(1, -80, 1, 0)
	name.BackgroundTransparency = 1
	name.Font = Enum.Font.Gotham
	name.Text = "-"
	name.TextColor3 = Color3.fromRGB(226, 229, 238)
	name.TextSize = 13
	name.TextTruncate = Enum.TextTruncate.AtEnd
	name.TextXAlignment = Enum.TextXAlignment.Left
	name.Parent = row

	local value = Instance.new("TextLabel")
	value.Name = "Value"
	value.AnchorPoint = Vector2.new(1, 0)
	value.Position = UDim2.new(1, 0, 0, 0)
	value.Size = UDim2.new(0, 70, 1, 0)
	value.BackgroundTransparency = 1
	value.Font = Enum.Font.GothamBold
	value.Text = "0"
	value.TextColor3 = Color3.fromRGB(${accent})
	value.TextSize = 13
	value.TextXAlignment = Enum.TextXAlignment.Right
	value.Parent = row

	rows[index] = { name = name, value = value }
end

local function statOf(target)
	local leaderstats = target:FindFirstChild("leaderstats")
	local holder = leaderstats and leaderstats:FindFirstChild(STAT)
	return holder and holder.Value or 0
end

local function refresh()
	local entries = {}
	for _, target in ipairs(Players:GetPlayers()) do
		if target ~= player or SHOW_SELF then
			table.insert(entries, { player = target, score = statOf(target) })
		end
	end
	table.sort(entries, function(a, b)
		return a.score > b.score
	end)

	for index, row in ipairs(rows) do
		local entry = entries[index]
		if entry then
			row.name.Text = entry.player.DisplayName
			row.value.Text = tostring(entry.score)
		else
			row.name.Text = "-"
			row.value.Text = "0"
		end
	end
end

refresh()
task.spawn(function()
	while true do
		refresh()
		task.wait(REFRESH)
	end
end)
"""


# --------------------------------------------------------------------------- #
#  World & hazards
# --------------------------------------------------------------------------- #

KILL_BRICK = r"""
${header}local Players = game:GetService("Players")
local CollectionService = game:GetService("CollectionService")

local TAG = "${tag}"
local DAMAGE = ${damage}
local INSTANT = ${instant}
local RESPAWN_DELAY = ${respawn_delay}
local EFFECT = "${effect}"

${tag_helper}${touch_helper}local function kill(character, humanoid, player)
	if EFFECT == "ragdoll" then
		-- Cheap ragdoll: drop the humanoid into physics and let it tumble.
		humanoid:ChangeState(Enum.HumanoidStateType.Physics)
		humanoid.PlatformStand = true
	elseif EFFECT == "launch" then
		local root = character:FindFirstChild("HumanoidRootPart")
		if root then
			local velocity = root.AssemblyLinearVelocity
			root.AssemblyLinearVelocity = Vector3.new(velocity.X * 0.4, 120, velocity.Z * 0.4)
		end
	end

	if INSTANT then
		humanoid.Health = 0
	else
		humanoid:TakeDamage(DAMAGE)
	end

	if RESPAWN_DELAY > 0 and player then
		task.delay(RESPAWN_DELAY, function()
			if character.Parent and humanoid.Parent and humanoid.Health > 0 then
				humanoid.Health = 0
			end
		end)
	end
end

watchTagged(TAG, function(part)
	part.CanTouch = true
	onTouchDebounced(part, 0.35, kill)
end)

print(string.format("[KillBrick] armed %d part(s)", #CollectionService:GetTagged(TAG)))
"""

CHECKPOINT = r"""
${header}local Players = game:GetService("Players")
local CollectionService = game:GetService("CollectionService")

local TAG = "${tag}"
local OFFSET_Y = ${offset}
local ANNOUNCE = ${announce}

local respawnPoints = {}

local function announce(player, index)
	if not ANNOUNCE then
		return
	end
	local message = Instance.new("Message")
	message.Text = "Checkpoint " .. index .. " reached!"
	message.Parent = player:FindFirstChild("PlayerGui") and player.PlayerGui
	task.delay(2.5, function()
		message:Destroy()
	end)
end

local ordered = {}
${tag_helper}local function register(part, index)
	part.CanTouch = true
	part.Touched:Connect(function(hit)
		local character = hit:FindFirstAncestorOfClass("Model")
		local player = character and Players:GetPlayerFromCharacter(character)
		if not player then
			return
		end
		local point = part.CFrame * CFrame.new(0, OFFSET_Y, 0)
		local current = respawnPoints[player]
		if current and (current.Position - point.Position).Magnitude < 4 then
			return
		end
		respawnPoints[player] = point
		announce(player, index)
	end)
end

watchTagged(TAG, function(part)
	table.insert(ordered, part)
	register(part, #ordered)
end)

Players.PlayerAdded:Connect(function(player)
	player.CharacterAdded:Connect(function(character)
		local point = respawnPoints[player]
		if not point then
			return
		end
		character:WaitForChild("HumanoidRootPart")
		task.wait()
		character:PivotTo(point)
		local root = character:FindFirstChild("HumanoidRootPart")
		if root then
			root.AssemblyLinearVelocity = Vector3.zero
		end
	end)
end)

Players.PlayerRemoving:Connect(function(player)
	respawnPoints[player] = nil
end)
"""

VOID_RESPAWN = r"""
${header}local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local KILL_Y = ${kill_y}
local MODE = "${mode}"
local CHECK_INTERVAL = 0.4

local function safePoint()
	local spawns = {}
	for _, part in ipairs(workspace:GetDescendants()) do
		if part:IsA("SpawnLocation") then
			table.insert(spawns, part)
		end
	end
	local spawn = spawns[math.random(1, math.max(1, #spawns))]
	return spawn and (spawn.CFrame * CFrame.new(0, 5, 0)) or CFrame.new(0, 20, 0)
end

local function rescue(character)
	local humanoid = character:FindFirstChildOfClass("Humanoid")
	if not humanoid then
		return
	end
	if MODE == "teleport" then
		local root = character:FindFirstChild("HumanoidRootPart")
		if root then
			character:PivotTo(safePoint())
			root.AssemblyLinearVelocity = Vector3.zero
		end
	else
		humanoid.Health = 0
	end
end

task.spawn(function()
	while true do
		task.wait(CHECK_INTERVAL)
		for _, player in ipairs(Players:GetPlayers()) do
			local character = player.Character
			local root = character and character:FindFirstChild("HumanoidRootPart")
			if root and root.Position.Y < KILL_Y then
				rescue(character)
			end
		end
	end
end)
"""

SPEED_PAD = r"""
${header}local Players = game:GetService("Players")
local CollectionService = game:GetService("CollectionService")
local TweenService = game:GetService("TweenService")

local TAG = "${tag}"
local BOOST_SPEED = ${speed}
local DURATION = ${duration}
local COOLDOWN = ${cooldown}
local FADE = ${fade}

${tag_helper}local function boost(character, humanoid)
	local original = humanoid.WalkSpeed
	humanoid.WalkSpeed = math.max(original, BOOST_SPEED)

	-- Each pad gives the boost its own generation number so overlapping
	-- boosts never restore the wrong WalkSpeed.
	local generation = (character:GetAttribute("RF_SpeedBoost") or 0) + 1
	character:SetAttribute("RF_SpeedBoost", generation)

	task.delay(DURATION, function()
		if humanoid.Parent and character:GetAttribute("RF_SpeedBoost") == generation then
			humanoid.WalkSpeed = original
			character:SetAttribute("RF_SpeedBoost", 0)
		end
	end)
end

watchTagged(TAG, function(part)
	part.CanTouch = true
	if FADE then
		TweenService:Create(part, TweenInfo.new(1.1, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true), {
			Transparency = 0.55,
		}):Play()
	end
	local last = {}
	part.Touched:Connect(function(hit)
		local character = hit:FindFirstAncestorOfClass("Model")
		local player = character and Players:GetPlayerFromCharacter(character)
		if not player then
			return
		end
		local now = os.clock()
		if last[player] and now - last[player] < COOLDOWN then
			return
		end
		last[player] = now
		local humanoid = character:FindFirstChildOfClass("Humanoid")
		if humanoid then
			boost(character, humanoid)
		end
	end)
end)
"""

JUMP_PAD = r"""
${header}local Players = game:GetService("Players")
local CollectionService = game:GetService("CollectionService")

local TAG = "${tag}"
local LAUNCH = ${launch}
local BOOST_JUMP_POWER = ${jump_power}
local DURATION = ${duration}
local COOLDOWN = ${cooldown}

${tag_helper}local function launchPlayer(character, humanoid)
	local root = character:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end

	if LAUNCH > 0 then
		local velocity = root.AssemblyLinearVelocity
		root.AssemblyLinearVelocity = Vector3.new(velocity.X, LAUNCH, velocity.Z)
	end

	if BOOST_JUMP_POWER > 0 and DURATION > 0 then
		local originalPower = humanoid.JumpPower
		local originalUseJumpPower = humanoid.UseJumpPower
		local originalHeight = humanoid.JumpHeight

		humanoid.UseJumpPower = true
		humanoid.JumpPower = math.max(originalPower, BOOST_JUMP_POWER)

		task.delay(DURATION, function()
			if humanoid.Parent then
				humanoid.JumpPower = originalPower
				humanoid.JumpHeight = originalHeight
				humanoid.UseJumpPower = originalUseJumpPower
			end
		end)
	end
end

watchTagged(TAG, function(part)
	part.CanTouch = true
	local last = {}
	part.Touched:Connect(function(hit)
		local character = hit:FindFirstAncestorOfClass("Model")
		local player = character and Players:GetPlayerFromCharacter(character)
		if not player then
			return
		end
		local now = os.clock()
		if last[player] and now - last[player] < COOLDOWN then
			return
		end
		last[player] = now
		local humanoid = character:FindFirstChildOfClass("Humanoid")
		if humanoid then
			launchPlayer(character, humanoid)
		end
	end)
end)
"""

TELEPORT_PADS = r"""
${header}local Players = game:GetService("Players")
local CollectionService = game:GetService("CollectionService")

local SOURCE_TAG = "${source_tag}"
local DESTINATION_TAG = "${destination_tag}"
local FIXED_DESTINATION = Vector3.new(${x}, ${y}, ${z})
local COOLDOWN = ${cooldown}
local SOUND_ENABLED = ${sound}

${tag_helper}local destinations = {}

local function collectDestination(part)
	destinations[#destinations + 1] = part
end

watchTagged(DESTINATION_TAG, collectDestination)

local function pickDestination()
	if #destinations > 0 then
		return destinations[math.random(1, #destinations)]
	end
	return nil
end

local function teleport(character)
	local root = character:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	local destination = pickDestination()
	local target
	if destination then
		target = destination.CFrame * CFrame.new(0, ${offset}, 0)
	else
		target = CFrame.new(FIXED_DESTINATION)
	end

	character:PivotTo(target)
	local velocity = root.AssemblyLinearVelocity
	root.AssemblyLinearVelocity = Vector3.new(velocity.X, 0, velocity.Z)

	if SOUND_ENABLED then
		local sound = Instance.new("Sound")
		sound.SoundId = "rbxasset://sounds/electronicpingshort.wav"
		sound.Volume = 0.6
		sound.Parent = root
		sound:Play()
		sound.Ended:Connect(function()
			sound:Destroy()
		end)
	end
end

watchTagged(SOURCE_TAG, function(part)
	part.CanTouch = true
	local last = {}
	part.Touched:Connect(function(hit)
		local character = hit:FindFirstAncestorOfClass("Model")
		local player = character and Players:GetPlayerFromCharacter(character)
		if not player then
			return
		end
		local now = os.clock()
		if last[player] and now - last[player] < COOLDOWN then
			return
		end
		last[player] = now
		teleport(character)
	end)
end)
"""

DAY_NIGHT = r"""
${header}local Lighting = game:GetService("Lighting")
local RunService = game:GetService("RunService")

local CYCLE_MINUTES = ${minutes}
local START_HOUR = ${start}
local SYNC_REAL_MINUTES = ${sync}
local APPLY_ATMOSPHERE = ${atmosphere}

if APPLY_ATMOSPHERE then
	Lighting.Brightness = 2
	Lighting.Ambient = Color3.fromRGB(70, 70, 80)
	Lighting.OutdoorAmbient = Color3.fromRGB(110, 110, 125)
	Lighting.EnvironmentDiffuseScale = 0.4
	Lighting.EnvironmentSpecularScale = 0.4
	if not Lighting:FindFirstChildOfClass("Atmosphere") then
		local atmosphere = Instance.new("Atmosphere")
		atmosphere.Density = 0.3
		atmosphere.Haze = 1.2
		atmosphere.Parent = Lighting
	end
end

if SYNC_REAL_MINUTES then
	-- Follow the player's real-world clock instead of a sped-up loop.
	task.spawn(function()
		while true do
			local now = os.date("*t")
			Lighting.ClockTime = now.hour + now.min / 60
			task.wait(20)
		end
	end)
else
	local clockTime = START_HOUR
	local secondsPerHour = (CYCLE_MINUTES * 60) / 24

	RunService.Heartbeat:Connect(function(deltaTime)
		clockTime = (clockTime + (CYCLE_MINUTES and deltaTime / secondsPerHour or 0)) % 24
		Lighting.ClockTime = clockTime
	end)
end
"""


# --------------------------------------------------------------------------- #
#  Game systems
# --------------------------------------------------------------------------- #

ROUND_SYSTEM = r"""
${header}local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local INTERMISSION = ${intermission}
local ROUND_LENGTH = ${round_length}
local MIN_PLAYERS = ${min_players}
local RESPAWN_ON_START = ${respawn}
local KILL_ON_END = ${kill_on_end}

-- Shared state, read by the companion client HUD (and by your own code).
local state = Instance.new("StringValue")
state.Name = "RoundState"
state.Value = "Intermission"
state.Parent = ReplicatedStorage

local timeLeft = Instance.new("IntValue")
timeLeft.Name = "RoundTimeLeft"
timeLeft.Parent = ReplicatedStorage

local roundNumber = Instance.new("IntValue")
roundNumber.Name = "RoundNumber"
roundNumber.Parent = ReplicatedStorage

local function countdown(seconds, label)
	state.Value = label
	for remaining = seconds, 0, -1 do
		timeLeft.Value = remaining
		task.wait(1)
	end
end

local function enoughPlayers()
	if MIN_PLAYERS <= 0 then
		return true
	end
	return #Players:GetPlayers() >= MIN_PLAYERS
end

local function preparePlayers()
	for _, player in ipairs(Players:GetPlayers()) do
		if RESPAWN_ON_START then
			player:LoadCharacter()
		end
	end
end

local function endRound()
	-- >>> Your win condition goes here. <<<
	-- Inspect your own state (a folder in ReplicatedStorage, player attributes,
	-- scores from StatsAPI, ...) and decide who won, then call StatsAPI.add.
	if KILL_ON_END then
		for _, player in ipairs(Players:GetPlayers()) do
			local humanoid = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
			if humanoid then
				humanoid.Health = 0
			end
		end
	end
	print(string.format("[Rounds] round %d finished", roundNumber.Value))
end

task.spawn(function()
	while true do
		countdown(INTERMISSION, "Intermission")
		if not enoughPlayers() then
			print("[Rounds] waiting for players...")
			timeLeft.Value = INTERMISSION
			task.wait(2)
			continue
		end

		roundNumber.Value += 1
		preparePlayers()
		countdown(ROUND_LENGTH, "Round")
		endRound()
	end
end)
"""

ROUND_HUD = r"""
${header}local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

local state = ReplicatedStorage:WaitForChild("RoundState")
local timeLeft = ReplicatedStorage:WaitForChild("RoundTimeLeft")
local roundNumber = ReplicatedStorage:WaitForChild("RoundNumber")

local gui = Instance.new("ScreenGui")
gui.Name = "RF_RoundHud"
gui.ResetOnSpawn = false
gui.Parent = playerGui

local frame = Instance.new("Frame")
frame.AnchorPoint = Vector2.new(0.5, 0)
frame.Position = UDim2.new(0.5, 0, 0, 14)
frame.Size = UDim2.fromOffset(260, 52)
frame.BackgroundColor3 = Color3.fromRGB(22, 24, 31)
frame.BackgroundTransparency = 0.12
frame.BorderSizePixel = 0
frame.Parent = gui
Instance.new("UICorner", frame).CornerRadius = UDim.new(0, 12)

local phase = Instance.new("TextLabel")
phase.Size = UDim2.new(1, 0, 0, 26)
phase.Position = UDim2.fromOffset(0, 6)
phase.BackgroundTransparency = 1
phase.Font = Enum.Font.GothamBold
phase.TextColor3 = Color3.fromRGB(245, 246, 250)
phase.TextSize = 16
phase.Text = "Intermission"
phase.Parent = frame

local timer = Instance.new("TextLabel")
timer.Size = UDim2.new(1, 0, 0, 16)
timer.Position = UDim2.fromOffset(0, 30)
timer.BackgroundTransparency = 1
timer.Font = Enum.Font.GothamMedium
timer.TextColor3 = Color3.fromRGB(160, 168, 186)
timer.TextSize = 13
timer.Text = "0s"
timer.Parent = frame

local function pad(seconds)
	return string.format("%d:%02d", math.floor(seconds / 60), seconds % 60)
end

local function refresh()
	local label = state.Value == "Round" and ("Round " .. roundNumber.Value) or "Next round in"
	phase.Text = label
	timer.Text = pad(math.max(0, timeLeft.Value))
	if state.Value == "Round" then
		phase.TextColor3 = Color3.fromRGB(255, 108, 100)
	else
		phase.TextColor3 = Color3.fromRGB(120, 220, 160)
	end
end

state.Changed:Connect(refresh)
timeLeft.Changed:Connect(refresh)
roundNumber.Changed:Connect(refresh)
refresh()
"""

CHAT_COMMANDS = r"""
${header}local Players = game:GetService("Players")

local PREFIX = "${prefix}"
local ADMIN_IDS = { ${admin_ids} }
local ALLOW_CREATOR = ${allow_creator}
local ALLOW_OTHERS_IF_EMPTY = ${open_when_empty}

local commandList = {}

local function isAdmin(player)
	for _, id in ipairs(ADMIN_IDS) do
		if player.UserId == id then
			return true
		end
	end
	if ALLOW_CREATOR and player.UserId == game.CreatorId then
		return true
	end
	if ALLOW_OTHERS_IF_EMPTY and #ADMIN_IDS == 0 then
		return true
	end
	return false
end

local function findPlayers(argument)
	if not argument or argument == "" then
		return {}
	end
	local found = {}
	for _, player in ipairs(Players:GetPlayers()) do
		if string.find(string.lower(player.Name), string.lower(argument), 1, true) then
			table.insert(found, player)
		end
	end
	return found
end

local function requireTarget(caller, argument)
	local targets = findPlayers(argument)
	if #targets == 0 then
		warn(string.format("[Admin] %s: no player matched '%s'", caller.Name, tostring(argument)))
		return nil
	end
	return targets[1]
end

commandList["heal"] = function(caller, args)
	local target = findPlayers(args[1])[1] or caller
	local humanoid = target.Character and target.Character:FindFirstChildOfClass("Humanoid")
	if humanoid then
		humanoid.Health = humanoid.MaxHealth
	end
end

commandList["speed"] = function(caller, args)
	local amount = tonumber(args[1]) or 16
	local target = findPlayers(args[2])[1] or caller
	local humanoid = target.Character and target.Character:FindFirstChildOfClass("Humanoid")
	if humanoid then
		humanoid.WalkSpeed = math.clamp(amount, 0, 512)
	end
end

commandList["give"] = function(caller, args)
	local amount = math.floor(tonumber(args[1]) or 100)
	local target = findPlayers(args[2])[1] or caller
	local ok, err = pcall(function()
		local StatsAPI = require(game:GetService("ReplicatedStorage").Shared.StatsAPI)
		StatsAPI.add(target, "${stat}", amount)
	end)
	if not ok then
		local leaderstats = target:FindFirstChild("leaderstats")
		local holder = leaderstats and leaderstats:FindFirstChild("${stat}")
		if holder then
			holder.Value = holder.Value + amount
		end
	end
end

commandList["tp"] = function(caller, args)
	if #args < 3 then
		return
	end
	local x, y, z = tonumber(args[1]), tonumber(args[2]), tonumber(args[3])
	if not (x and y and z) then
		return
	end
	local character = caller.Character
	if character then
		character:PivotTo(CFrame.new(x, y, z))
	end
end

commandList["bring"] = function(caller, args)
	local target = requireTarget(caller, args[1])
	local character = caller.Character
	if target and target.Character and character then
		target.Character:PivotTo(character:GetPivot() * CFrame.new(0, 0, -4))
	end
end

commandList["respawn"] = function(caller, args)
	local target = findPlayers(args[1])[1] or caller
	target:LoadCharacter()
end

commandList["kick"] = function(caller, args)
	local target = findPlayers(args[1])[1]
	if target and target ~= caller then
		target:Kick("Kicked by " .. caller.Name)
	end
end

commandList["god"] = function(caller, args)
	local target = findPlayers(args[1])[1] or caller
	local humanoid = target.Character and target.Character:FindFirstChildOfClass("Humanoid")
	if humanoid then
		humanoid.MaxHealth = math.huge
		humanoid.Health = math.huge
	end
end

local function helpText()
	local names = {}
	for name in pairs(commandList) do
		table.insert(names, name)
	end
	table.sort(names)
	return PREFIX .. table.concat(names, "  " .. PREFIX)
end

local function handle(caller, message)
	if string.sub(message, 1, #PREFIX) ~= PREFIX then
		return
	end
	if not isAdmin(caller) then
		return
	end

	local parts = {}
	for word in string.gmatch(string.sub(message, #PREFIX + 1), "%S+") do
		table.insert(parts, word)
	end

	local command = table.remove(parts, 1)
	if not command then
		return
	end
	command = string.lower(command)

	if command == "help" or command == "commands" then
		print("[Admin]", helpText())
		return
	end

	local handler = commandList[command]
	if handler then
		local ok, err = pcall(handler, caller, parts)
		if not ok then
			warn(string.format("[Admin] %s failed: %s", command, tostring(err)))
		end
	end
end

Players.PlayerAdded:Connect(function(player)
	player.Chatted:Connect(function(message)
		handle(player, message)
	end)
end)
"""

TEAM_ASSIGN = r"""
${header}local Players = game:GetService("Players")

local TEAMS = {
	{ name = "${team_a}", color = "${color_a}" },
	{ name = "${team_b}", color = "${color_b}" },
}
local AUTO_BALANCE = ${balance}
local RESPAWN_ON_SWITCH = ${respawn}

local function ensureTeam(definition)
	local team = game.Teams:FindFirstChild(definition.name)
	if not team then
		team = Instance.new("Team")
		team.Name = definition.name
		team.Parent = game.Teams
	end
	team.TeamColor = BrickColor.new(definition.color)
	team.AutoAssignable = true
	return team
end

local teams = {}
for _, definition in ipairs(TEAMS) do
	table.insert(teams, ensureTeam(definition))
end

local function smallestTeam()
	if not AUTO_BALANCE then
		return teams[math.random(1, #teams)]
	end
	local best = teams[1]
	for _, team in ipairs(teams) do
		if #team:GetPlayers() < #best:GetPlayers() then
			best = team
		end
	end
	return best
end

local function assign(player)
	if player.Team then
		return
	end
	local team = smallestTeam()
	player.Team = team
	player.TeamColor = team.TeamColor
	player.Neutral = false
	if RESPAWN_ON_SWITCH and player.Character then
		task.wait(0.2)
		player:LoadCharacter()
	end
end

Players.PlayerAdded:Connect(assign)

for _, player in ipairs(Players:GetPlayers()) do
	assign(player)
end
"""


# --------------------------------------------------------------------------- #
#  Shared stats plumbing
# --------------------------------------------------------------------------- #

STATS_MODULE = r"""
--!nonstrict
${header}local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local STORE_NAME = "${store}"
local AUTOSAVE_SECONDS = ${autosave}
local STAT_NAMES = { ${stats} }
local START_VALUE = ${start_value}

local StatsAPI = {}
local cache = {}
local store = DataStoreService:GetDataStore(STORE_NAME)
local started = false

local function isStudio()
	return RunService:IsStudio()
end

local function cacheKey(player)
	return "u" .. tostring(player.UserId)
end

local function blankData()
	local values = {}
	for _, statName in ipairs(STAT_NAMES) do
		values[statName] = START_VALUE
	end
	return values
end

function StatsAPI.dataFor(player)
	local key = cacheKey(player)
	if cache[key] then
		return cache[key]
	end

	local values = blankData()
	if not isStudio() then
		local ok, saved = pcall(store.GetAsync, store, key)
		if ok and type(saved) == "table" then
			for statName in pairs(values) do
				if type(saved[statName]) == "number" then
					values[statName] = math.max(0, math.floor(saved[statName]))
				end
			end
		elseif not ok then
			warn("[StatsAPI] load failed for " .. player.Name .. ": " .. tostring(saved))
		end
	end

	cache[key] = values
	return values
end

local function push(player)
	local data = StatsAPI.dataFor(player)
	local leaderstats = player:FindFirstChild("leaderstats")
	if not leaderstats then
		return
	end
	for _, statName in ipairs(STAT_NAMES) do
		local holder = leaderstats:FindFirstChild(statName)
		if holder then
			holder.Value = data[statName]
		end
	end
end

function StatsAPI.setup(player)
	local data = StatsAPI.dataFor(player)

	local leaderstats = player:FindFirstChild("leaderstats")
	if not leaderstats then
		leaderstats = Instance.new("Folder")
		leaderstats.Name = "leaderstats"
		leaderstats.Parent = player
	end

	for _, statName in ipairs(STAT_NAMES) do
		local holder = leaderstats:FindFirstChild(statName)
		if not holder then
			holder = Instance.new("IntValue")
			holder.Name = statName
			holder.Parent = leaderstats
		end
		holder.Value = data[statName]
	end

	return data
end

function StatsAPI.get(player, statName)
	local data = StatsAPI.dataFor(player)
	return data[statName or STAT_NAMES[1]] or 0
end

function StatsAPI.set(player, statName, value)
	local data = StatsAPI.dataFor(player)
	if data[statName] == nil then
		warn(string.format("[StatsAPI] unknown stat %q - this project has: %s", tostring(statName), table.concat(STAT_NAMES, ", ")))
		return 0
	end
	data[statName] = math.max(0, math.floor(tonumber(value) or 0))
	push(player)
	return data[statName]
end

function StatsAPI.add(player, statName, delta)
	return StatsAPI.set(player, statName, StatsAPI.get(player, statName) + (tonumber(delta) or 0))
end

function StatsAPI.awardAll(statName, delta)
	for _, player in ipairs(Players:GetPlayers()) do
		StatsAPI.add(player, statName, delta)
	end
end

function StatsAPI.save(player)
	local key = cacheKey(player)
	local data = cache[key]
	if not data or isStudio() then
		return
	end
	local ok, err = pcall(store.SetAsync, store, key, data)
	if not ok then
		warn("[StatsAPI] save failed for " .. player.Name .. ": " .. tostring(err))
	end
end

function StatsAPI.saveAll()
	for _, player in ipairs(Players:GetPlayers()) do
		StatsAPI.save(player)
	end
end

function StatsAPI.start()
	if started then
		return
	end
	started = true

	for _, player in ipairs(Players:GetPlayers()) do
		StatsAPI.setup(player)
	end
	Players.PlayerAdded:Connect(StatsAPI.setup)

	Players.PlayerRemoving:Connect(function(player)
		StatsAPI.save(player)
		cache[cacheKey(player)] = nil
	end)

	game:BindToClose(function()
		if isStudio() then
			return
		end
		StatsAPI.saveAll()
		task.wait(2)
	end)

	task.spawn(function()
		while true do
			task.wait(AUTOSAVE_SECONDS)
			StatsAPI.saveAll()
		end
	end)
end

return StatsAPI
"""

STATS_BOOTSTRAP = r"""
--!nonstrict
${header}local ReplicatedStorage = game:GetService("ReplicatedStorage")

local StatsAPI = require(ReplicatedStorage.Shared.StatsAPI)

-- Creates leaderstats for everyone who joins and turns on autosaving.
StatsAPI.start()

print("[Stats] leaderstats ready: ${stats}")
"""


# --------------------------------------------------------------------------- #
#  Generator functions
# --------------------------------------------------------------------------- #


def _gen_sprint(params, ctx):
    code = _fill(
        SPRINT,
        {
            "header": header(
                "Sprint - hold a key to run faster (LocalScript)",
                "StarterPlayer > StarterPlayerScripts",
                "Runs on the client so the server never has to trust it.",
            ),
            "walk": lint(params["walk_speed"], 16),
            "sprint": lint(params["sprint_speed"], 30),
            "key": str(params["key"]).replace(" ", ""),
            "stamina": lua_bool(params["stamina"]),
            "max_stamina": lint(params["max_stamina"], 5),
            "stamina_rate": lint(params["stamina_rate"], 1),
            "stamina_loop": SPRINT_STAMINA_LOOP if params["stamina"] else "",
        },
    )
    return [Script("StarterPlayer/StarterPlayerScripts/Movement/Sprint.client.luau", "client", code)]


def _gen_double_jump(params, ctx):
    code = _fill(
        DOUBLE_JUMP,
        {
            "header": header(
                "Double jump - extra jumps while airborne (LocalScript)",
                "StarterPlayer > StarterPlayerScripts",
            ),
            "max_jumps": int(num(params["max_jumps"], 2)),
            "jump_power": lint(params["jump_power"], 50),
            "mobile": lua_bool(params["mobile_button"]),
            "mobile_block": DOUBLE_JUMP_MOBILE if params["mobile_button"] else "",
        },
    )
    return [Script("StarterPlayer/StarterPlayerScripts/Movement/DoubleJump.client.luau", "client", code)]


def _gen_dash(params, ctx):
    code = _fill(
        DASH,
        {
            "header": header(
                "Dash - quick burst of speed with a cooldown (LocalScript)",
                "StarterPlayer > StarterPlayerScripts",
            ),
            "key": str(params["key"]).replace(" ", ""),
            "speed": lint(params["speed"], 90),
            "time": lint(params["duration"], 0.2),
            "cooldown": lint(params["cooldown"], 1.5),
            "allow_air": lua_bool(params["allow_in_air"]),
        },
    )
    return [Script("StarterPlayer/StarterPlayerScripts/Movement/Dash.client.luau", "client", code)]


def _gen_coin_collect(params, ctx):
    code = _fill(
        COIN_COLLECT,
        {
            "header": header(
                "Coin collect - grab coins, earn currency (ServerScript)",
                "ServerScriptService",
                "Awards score on the SERVER, so exploiters cannot fake pickups.",
            ),
            "tag": slugify(params["tag"], "Coin"),
            "stat": params["stat"],
            "amount": int(num(params["amount"], 1)),
            "respawn": lint(params["respawn"], 12),
            "spin": lint(params["spin"], 90),
            "float": lint(params["float"], 0.5),
            "tag_helper": TAG_HELPER,
        },
    )
    return [Script("ServerScriptService/Features/CoinCollect.server.luau", "server", code)]


def _gen_income(params, ctx):
    code = _fill(
        INCOME,
        {
            "header": header(
                "Passive income - pay players on a timer (ServerScript)",
                "ServerScriptService",
            ),
            "stat": params["stat"],
            "amount": int(num(params["amount"], 1)),
            "interval": lint(params["interval"], 5),
            "cap": int(num(params["cap"], 1000)),
            "growth": lua_bool(params["scale_with_time"]),
        },
    )
    return [Script("ServerScriptService/Features/Income.server.luau", "server", code)]


def _gen_leaderboard_gui(params, ctx):
    accent = params["accent"]
    palette = {
        "gold": "255, 196, 92",
        "green": "120, 220, 160",
        "blue": "110, 170, 255",
        "red": "255, 120, 110",
        "white": "235, 238, 246",
    }
    code = _fill(
        LEADERBOARD_GUI,
        {
            "header": header(
                "Leaderboard HUD - top players by a leaderstat (LocalScript)",
                "StarterPlayer > StarterPlayerScripts",
            ),
            "stat": params["stat"],
            "rows": int(num(params["rows"], 5)),
            "refresh": lint(params["refresh"], 1),
            "self": lua_bool(params["show_self"]),
            "title": q(params["title"]),
            "accent": palette.get(str(accent), palette["gold"]),
        },
    )
    return [Script("StarterPlayer/StarterPlayerScripts/UI/Leaderboard.client.luau", "client", code)]


def _gen_kill_brick(params, ctx):
    code = _fill(
        KILL_BRICK,
        {
            "header": header(
                "Kill brick - parts that hurt on touch (ServerScript)",
                "ServerScriptService",
            ),
            "tag": slugify(params["tag"], "KillBrick"),
            "damage": lint(params["damage"], 100),
            "instant": lua_bool(params["instant_kill"]),
            "respawn_delay": lint(params["finish_delay"], 0),
            "effect": params["effect"],
            "tag_helper": TAG_HELPER,
            "touch_helper": TOUCH_HELPER,
        },
    )
    return [Script("ServerScriptService/World/KillBrick.server.luau", "server", code)]


def _gen_checkpoint(params, ctx):
    code = _fill(
        CHECKPOINT,
        {
            "header": header(
                "Checkpoints - respawn where you got to (ServerScript)",
                "ServerScriptService",
            ),
            "tag": slugify(params["tag"], "Checkpoint"),
            "offset": lint(params["offset_y"], 4),
            "announce": lua_bool(params["announce"]),
            "tag_helper": TAG_HELPER,
        },
    )
    return [Script("ServerScriptService/World/Checkpoints.server.luau", "server", code)]


def _gen_void_respawn(params, ctx):
    code = _fill(
        VOID_RESPAWN,
        {
            "header": header(
                "Void rescue - catch players who fall out of the map (ServerScript)",
                "ServerScriptService",
            ),
            "kill_y": lint(params["kill_y"], -50),
            "mode": params["mode"],
        },
    )
    return [Script("ServerScriptService/World/VoidRescue.server.luau", "server", code)]


def _gen_speed_pad(params, ctx):
    code = _fill(
        SPEED_PAD,
        {
            "header": header(
                "Speed pad - temporary speed boost on touch (ServerScript)",
                "ServerScriptService",
            ),
            "tag": slugify(params["tag"], "SpeedPad"),
            "speed": lint(params["speed"], 45),
            "duration": lint(params["duration"], 4),
            "cooldown": lint(params["cooldown"], 1),
            "fade": lua_bool(params["pulse"]),
            "tag_helper": TAG_HELPER,
        },
    )
    return [Script("ServerScriptService/World/SpeedPad.server.luau", "server", code)]


def _gen_jump_pad(params, ctx):
    code = _fill(
        JUMP_PAD,
        {
            "header": header(
                "Jump pad - launch players into the air (ServerScript)",
                "ServerScriptService",
            ),
            "tag": slugify(params["tag"], "JumpPad"),
            "launch": lint(params["launch"], 120),
            "jump_power": lint(params["jump_power"], 0),
            "duration": lint(params["jump_duration"], 0),
            "cooldown": lint(params["cooldown"], 0.5),
            "tag_helper": TAG_HELPER,
        },
    )
    return [Script("ServerScriptService/World/JumpPad.server.luau", "server", code)]


def _gen_teleport_pads(params, ctx):
    code = _fill(
        TELEPORT_PADS,
        {
            "header": header(
                "Teleport pads - hop between two locations (ServerScript)",
                "ServerScriptService",
            ),
            "source_tag": slugify(params["source_tag"], "TeleportPadA"),
            "destination_tag": slugify(params["destination_tag"], "TeleportPadB"),
            "x": lint(params["x"], 0),
            "y": lint(params["y"], 10),
            "z": lint(params["z"], 0),
            "offset": lint(params["offset_y"], 5),
            "cooldown": lint(params["cooldown"], 1),
            "sound": lua_bool(params["sound"]),
            "tag_helper": TAG_HELPER,
        },
    )
    return [Script("ServerScriptService/World/TeleportPads.server.luau", "server", code)]


def _gen_day_night(params, ctx):
    code = _fill(
        DAY_NIGHT,
        {
            "header": header(
                "Day/night cycle - moving sun and atmosphere (ServerScript)",
                "ServerScriptService",
            ),
            "minutes": lint(params["cycle_minutes"], 10),
            "start": lint(params["start_hour"], 14),
            "sync": lua_bool(params["follow_real_time"]),
            "atmosphere": lua_bool(params["tune_lighting"]),
        },
    )
    return [Script("ServerScriptService/World/DayNightCycle.server.luau", "server", code)]


def _gen_round_system(params, ctx):
    server = _fill(
        ROUND_SYSTEM,
        {
            "header": header(
                "Round system - intermission / round loop (ServerScript)",
                "ServerScriptService",
                "Starts a round, flips ReplicatedStorage.RoundState and ends the round.",
            ),
            "intermission": int(num(params["intermission"], 20)),
            "round_length": int(num(params["round_length"], 120)),
            "min_players": int(num(params["min_players"], 2)),
            "respawn": lua_bool(params["respawn_at_start"]),
            "kill_on_end": lua_bool(params["kill_at_end"]),
        },
    )
    hud = _fill(
        ROUND_HUD,
        {
            "header": header(
                "Round HUD - shows the current phase + countdown (LocalScript)",
                "StarterPlayer > StarterPlayerScripts",
            ),
        },
    )
    return [
        Script("ServerScriptService/Systems/RoundSystem.server.luau", "server", server),
        Script("StarterPlayer/StarterPlayerScripts/UI/RoundHud.client.luau", "client", hud),
    ]


def _gen_chat_commands(params, ctx):
    ids = [item.strip() for item in str(params["admin_ids"]).replace(";", ",").split(",") if item.strip()]
    ids = [item for item in ids if item.isdigit()]
    code = _fill(
        CHAT_COMMANDS,
        {
            "header": header(
                "Admin chat commands (ServerScript)",
                "ServerScriptService",
                "Type the prefix in chat, e.g. ':speed 40', ':give 500', ':help'.",
            ),
            "prefix": str(params["prefix"])[:3] or ":",
            "admin_ids": ", ".join(ids),
            "allow_creator": lua_bool(params["allow_creator"]),
            "open_when_empty": lua_bool(params["allow_when_empty"]),
            "stat": params["stat"],
        },
    )
    return [Script("ServerScriptService/Systems/AdminCommands.server.luau", "server", code)]


def _gen_team_assign(params, ctx):
    code = _fill(
        TEAM_ASSIGN,
        {
            "header": header(
                "Team assigner - create teams and balance joins (ServerScript)",
                "ServerScriptService",
                "Add a SpawnLocation per team and set its TeamColor to match, so each\n\tteam spawns in its own area.",
            ),
            "team_a": q(params["team_a"]),
            "team_b": q(params["team_b"]),
            "color_a": q(params["color_a"]),
            "color_b": q(params["color_b"]),
            "balance": lua_bool(params["balance"]),
            "respawn": lua_bool(params["respawn_on_switch"]),
        },
    )
    return [Script("ServerScriptService/Systems/Teams.server.luau", "server", code)]


def build_stats_module(settings: dict) -> str:
    stats = [settings["stat"], settings["currency"]]
    return _fill(
        STATS_MODULE,
        {
            "header": header(
                f"StatsAPI - leaderstats + DataStore saving ({settings['stat']}, {settings['currency']})",
                "ReplicatedStorage > Shared",
                "Require it from server scripts only.",
            ),
            "store": f"RF_Stats_{slugify(settings['stat'], 'Points')}_v1",
            "autosave": int(settings["autosave"]),
            "stats": lua_list(stats),
            "start_value": int(settings["start_value"]),
        },
    )


def build_stats_bootstrap(settings: dict) -> str:
    return _fill(
        STATS_BOOTSTRAP,
        {
            "header": header(
                "Stats bootstrap - start the shared stats module (ServerScript)",
                "ServerScriptService",
            ),
            "stats": ", ".join([settings["stat"], settings["currency"]]),
        },
    )


# --------------------------------------------------------------------------- #
#  Registry
# --------------------------------------------------------------------------- #

KEY_OPTIONS = (
    ("LeftShift", "Left Shift"),
    ("RightShift", "Right Shift"),
    ("Q", "Q"),
    ("E", "E"),
    ("F", "F"),
    ("G", "G"),
    ("C", "C"),
    ("LeftControl", "Left Ctrl"),
    ("LeftAlt", "Left Alt"),
    ("Space", "Space"),
    ("R", "R"),
    ("T", "T"),
    ("V", "V"),
    ("X", "X"),
    ("Z", "Z"),
)

ALL_FEATURES: tuple[Feature, ...] = (
    # ---- Movement -------------------------------------------------------- #
    Feature(
        id="sprint",
        name="Sprint",
        category="Movement",
        summary="Hold a key to run faster, with optional stamina so players cannot sprint forever.",
        params=(
            Param("key", "Sprint key", "select", "LeftShift", KEY_OPTIONS),
            Param("walk_speed", "Normal WalkSpeed", "number", 16, minimum=1, maximum=200, step=1),
            Param("sprint_speed", "Sprint WalkSpeed", "number", 30, minimum=1, maximum=400, step=1),
            Param("stamina", "Use stamina drain", "bool", False),
            Param("max_stamina", "Max stamina (seconds)", "number", 5, minimum=1, maximum=60, step=1),
            Param("stamina_rate", "Drain per second", "number", 1, minimum=0.1, maximum=20, step=0.1),
        ),
        generate=_gen_sprint,
    ),
    Feature(
        id="double_jump",
        name="Double jump",
        category="Movement",
        summary="Extra jumps in mid-air, with an optional on-screen button for mobile players.",
        params=(
            Param("max_jumps", "Total jumps (1 = double)", "number", 2, minimum=2, maximum=5, step=1),
            Param("jump_power", "Extra jump power", "number", 50, minimum=0, maximum=200, step=1),
            Param("mobile_button", "Add mobile jump button", "bool", True),
        ),
        generate=_gen_double_jump,
    ),
    Feature(
        id="dash",
        name="Dash",
        category="Movement",
        summary="Short burst of speed towards where the player is aiming, with a cooldown.",
        params=(
            Param("key", "Dash key", "select", "Q", KEY_OPTIONS),
            Param("speed", "Dash speed", "number", 90, minimum=20, maximum=500, step=5),
            Param("duration", "Dash duration (s)", "number", 0.2, minimum=0.05, maximum=2, step=0.05),
            Param("cooldown", "Cooldown (s)", "number", 1.5, minimum=0, maximum=30, step=0.1),
            Param("allow_in_air", "Allow dashing mid-air", "bool", True),
        ),
        generate=_gen_dash,
    ),
    # ---- Player stats ---------------------------------------------------- #
    Feature(
        id="leaderstats",
        name="Leaderstats + saving",
        category="Player Stats",
        summary="Two saved leaderboard stats for every player, with DataStore saving and autosave.",
        params=(
            Param("stat_name", "Score stat name", "text", "Points"),
            Param("currency_name", "Currency stat name", "text", "Cash"),
            Param("start_value", "Starting value", "number", 0, minimum=0, maximum=100000, step=1),
            Param("autosave", "Autosave every (s)", "number", 120, minimum=30, maximum=600, step=10),
        ),
        notes=(
            "Stats live in ReplicatedStorage.Shared.StatsAPI - call StatsAPI.add(player, \"Points\", 10) from any server script.",
            "In Studio, DataStores only work with 'Enable Studio Access to API Services' ticked.",
        ),
        generate=lambda params, ctx: [],
    ),
    Feature(
        id="coin_collect",
        name="Collectable coins",
        category="Player Stats",
        summary="Coins that spin, pay out on touch and respawn after a delay.",
        params=(
            Param("tag", "Coin tag / name", "text", "Coin"),
            Param(
                "stat",
                "Pay into stat",
                "text",
                "Cash",
                help="Must match a leaderstat name (Cash or Points by default).",
            ),
            Param("amount", "Coins are worth", "number", 1, minimum=1, maximum=10000, step=1),
            Param("respawn", "Respawn after (s)", "number", 12, minimum=0, maximum=600, step=1),
            Param("spin", "Spin speed (deg/s)", "number", 90, minimum=0, maximum=720, step=10),
            Param("float", "Float height", "number", 0.5, minimum=0, maximum=5, step=0.1),
        ),
        notes=(
            "Tag your coin parts 'Coin' in the Studio Tag Editor, or simply name them Coin.",
            "Coins get anchored and CanCollide=false automatically when the script finds them.",
        ),
        generate=_gen_coin_collect,
    ),
    Feature(
        id="income",
        name="Passive income",
        category="Player Stats",
        summary="Pay every player on a timer, optionally scaling up the longer they stay.",
        params=(
            Param(
                "stat",
                "Pay into stat",
                "text",
                "Cash",
                help="Must match a leaderstat name (Cash or Points by default).",
            ),
            Param("amount", "Amount per payout", "number", 5, minimum=1, maximum=10000, step=1),
            Param("interval", "Payout every (s)", "number", 5, minimum=1, maximum=300, step=1),
            Param("scale_with_time", "Scale with minutes played", "bool", False),
            Param("cap", "Max payout per tick", "number", 1000, minimum=1, maximum=100000, step=10),
        ),
        generate=_gen_income,
    ),
    Feature(
        id="leaderboard_gui",
        name="Leaderboard HUD",
        category="Player Stats",
        summary="On-screen top players board that reads leaderstats and refreshes on a timer.",
        params=(
            Param(
                "stat",
                "Stat to rank by",
                "text",
                "Points",
                help="Must match a leaderstat name (Points or Cash by default).",
            ),
            Param("title", "Board title", "text", "TOP PLAYERS"),
            Param("rows", "Rows shown", "number", 5, minimum=1, maximum=15, step=1),
            Param("refresh", "Refresh every (s)", "number", 1, minimum=0.25, maximum=30, step=0.25),
            Param("show_self", "Show the local player", "bool", True),
            Param(
                "accent",
                "Accent colour",
                "select",
                "gold",
                (
                    ("gold", "Gold"),
                    ("green", "Green"),
                    ("blue", "Blue"),
                    ("red", "Red"),
                    ("white", "White"),
                ),
            ),
        ),
        generate=_gen_leaderboard_gui,
    ),
    # ---- World & hazards -------------------------------------------------- #
    Feature(
        id="kill_brick",
        name="Kill bricks",
        category="World & Hazards",
        summary="Lava, spikes and traps that damage or instantly kill anyone who touches them.",
        params=(
            Param("tag", "Brick tag / name", "text", "KillBrick"),
            Param("instant_kill", "Instant kill", "bool", True),
            Param("damage", "Damage (when not instant)", "number", 25, minimum=1, maximum=1000, step=1),
            Param("finish_delay", "Finish them off after (s)", "number", 0, minimum=0, maximum=10, step=0.5),
            Param(
                "effect",
                "On-hit effect",
                "select",
                "none",
                (("none", "None"), ("ragdoll", "Ragdoll"), ("launch", "Launch")),
            ),
        ),
        notes=("Tag parts 'KillBrick' with the Tag Editor, or name them KillBrick.",),
        generate=_gen_kill_brick,
    ),
    Feature(
        id="checkpoint",
        name="Checkpoints",
        category="World & Hazards",
        summary="Players respawn at the last checkpoint they touched instead of the start.",
        params=(
            Param("tag", "Checkpoint tag / name", "text", "Checkpoint"),
            Param("offset_y", "Spawn height offset", "number", 4, minimum=0, maximum=50, step=1),
            Param("announce", "Show 'checkpoint reached'", "bool", True),
        ),
        notes=(
            "Works with any part shape - it remembers the exact CFrame.",
            "Progress resets when the player leaves the server (add DataStore saving if you need it to persist).",
        ),
        generate=_gen_checkpoint,
    ),
    Feature(
        id="void_rescue",
        name="Void rescue",
        category="World & Hazards",
        summary="Catches players who fall below a Y height and either kills or teleports them back.",
        params=(
            Param("kill_y", "Trigger below Y", "number", -50, minimum=-500, maximum=100, step=5),
            Param(
                "mode",
                "What happens",
                "select",
                "kill",
                (("kill", "Respawn them"), ("teleport", "Teleport to a spawn")),
            ),
        ),
        generate=_gen_void_respawn,
    ),
    Feature(
        id="speed_pad",
        name="Speed pads",
        category="World & Hazards",
        summary="Touch a pad to get a temporary speed boost, with an optional pulsing effect.",
        params=(
            Param("tag", "Pad tag / name", "text", "SpeedPad"),
            Param("speed", "Boosted WalkSpeed", "number", 45, minimum=16, maximum=300, step=1),
            Param("duration", "Boost lasts (s)", "number", 4, minimum=0.5, maximum=60, step=0.5),
            Param("cooldown", "Re-trigger cooldown (s)", "number", 1, minimum=0, maximum=30, step=0.5),
            Param("pulse", "Pulse the pad's transparency", "bool", True),
        ),
        generate=_gen_speed_pad,
    ),
    Feature(
        id="jump_pad",
        name="Jump pads",
        category="World & Hazards",
        summary="Launch players skywards, or hand them a temporary super jump.",
        params=(
            Param("tag", "Pad tag / name", "text", "JumpPad"),
            Param("launch", "Upward launch velocity", "number", 120, minimum=0, maximum=500, step=5),
            Param("jump_power", "Temporary JumpPower (0 = off)", "number", 0, minimum=0, maximum=300, step=5),
            Param("jump_duration", "JumpPower lasts (s)", "number", 0, minimum=0, maximum=60, step=0.5),
            Param("cooldown", "Re-trigger cooldown (s)", "number", 0.5, minimum=0, maximum=10, step=0.5),
        ),
        generate=_gen_jump_pad,
    ),
    Feature(
        id="teleport_pads",
        name="Teleport pads",
        category="World & Hazards",
        summary="Two-way portals between tagged pads, with a fallback fixed destination.",
        params=(
            Param("source_tag", "Entry pad tag", "text", "TeleportPadA"),
            Param("destination_tag", "Exit pad tag", "text", "TeleportPadB"),
            Param("x", "Fallback X", "number", 0, minimum=-10000, maximum=10000, step=1),
            Param("y", "Fallback Y", "number", 10, minimum=-10000, maximum=10000, step=1),
            Param("z", "Fallback Z", "number", 0, minimum=-10000, maximum=10000, step=1),
            Param("offset_y", "Arrival height offset", "number", 5, minimum=0, maximum=50, step=1),
            Param("cooldown", "Cooldown (s)", "number", 1, minimum=0, maximum=30, step=0.5),
            Param("sound", "Play teleport sound", "bool", True),
        ),
        notes=("Tag the exit pads too, or the script uses the fallback coordinates.",),
        generate=_gen_teleport_pads,
    ),
    Feature(
        id="day_night",
        name="Day / night cycle",
        category="World & Hazards",
        summary="A moving sun with optional atmosphere tuning, or follow the player's real clock.",
        params=(
            Param("cycle_minutes", "Full cycle length (minutes)", "number", 10, minimum=1, maximum=240, step=1),
            Param("start_hour", "Starting hour (0-24)", "number", 14, minimum=0, maximum=24, step=0.5),
            Param("follow_real_time", "Follow the player's real time", "bool", False),
            Param("tune_lighting", "Set up lighting + atmosphere", "bool", True),
        ),
        generate=_gen_day_night,
    ),
    # ---- Game systems ----------------------------------------------------- #
    Feature(
        id="round_system",
        name="Round system",
        category="Game Systems",
        summary="Intermission / round loop that broadcasts its state and a countdown to every client.",
        params=(
            Param("intermission", "Intermission (s)", "number", 20, minimum=5, maximum=600, step=1),
            Param("round_length", "Round length (s)", "number", 120, minimum=10, maximum=3600, step=5),
            Param("min_players", "Minimum players to start", "number", 1, minimum=0, maximum=50, step=1),
            Param("respawn_at_start", "Respawn everyone at round start", "bool", True),
            Param("kill_at_end", "Respawn everyone at round end", "bool", True),
        ),
        notes=(
            "Drop your win condition into the marked endRound() function.",
            "State is published as ReplicatedStorage.RoundState / RoundTimeLeft for your own code.",
        ),
        generate=_gen_round_system,
    ),
    Feature(
        id="chat_commands",
        name="Admin chat commands",
        category="Game Systems",
        summary="Prefix commands for healing, giving currency, teleporting, respawning and kicking.",
        params=(
            Param("prefix", "Command prefix", "text", ":"),
            Param("admin_ids", "Admin UserIds (comma separated)", "text", ""),
            Param("allow_creator", "Allow the experience owner", "bool", True),
            Param("allow_when_empty", "If no UserIds given, allow everyone", "bool", False),
            Param(
                "stat",
                "Stat used by :give",
                "text",
                "Cash",
                help="Must match a leaderstat name (Cash or Points by default).",
            ),
        ),
        notes=(
            "Commands: :help :heal :speed :give :tp :bring :respawn :kick :god",
            "Works with the legacy chat bar; with TextChatService it still fires for default channel messages.",
        ),
        generate=_gen_chat_commands,
    ),
    Feature(
        id="team_assign",
        name="Team assigner",
        category="Game Systems",
        summary="Creates two teams, colours them, and drops joining players into the smaller one.",
        params=(
            Param("team_a", "Team 1 name", "text", "Red Team"),
            Param("color_a", "Team 1 colour", "text", "Bright red"),
            Param("team_b", "Team 2 name", "text", "Blue Team"),
            Param("color_b", "Team 2 colour", "text", "Bright blue"),
            Param("balance", "Balance team sizes", "bool", True),
            Param("respawn_on_switch", "Respawn on assignment", "bool", False),
        ),
        generate=_gen_team_assign,
    ),
)

FEATURES_BY_ID = {feature.id: feature for feature in ALL_FEATURES}
