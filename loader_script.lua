-- ========================================
-- 🔐 KEY VALIDATION
-- ========================================
local validationURL = "https://bot-5iih.onrender.com/validate"  -- ✅ CORRECT

local key = getgenv().Key
if not key or key == "" then
    warn("❌ No key provided. Script will not load.")
    return
end

-- Function to show error screen
local function showErrorScreen(errorMessage)
    local Players = game:GetService("Players")
    local CoreGui = game:GetService("CoreGui")
    local LocalPlayer = Players.LocalPlayer
    
    -- Create error GUI
    local ErrorGui = Instance.new("ScreenGui")
    ErrorGui.Name = "ErrorScreen"
    ErrorGui.ResetOnSpawn = false
    ErrorGui.Parent = CoreGui
    
    -- Background frame
    local BackgroundFrame = Instance.new("Frame")
    BackgroundFrame.Size = UDim2.new(1, 0, 1, 0)
    BackgroundFrame.BackgroundColor3 = Color3.fromRGB(0, 0, 0)
    BackgroundFrame.BackgroundTransparency = 0.5
    BackgroundFrame.Parent = ErrorGui
    
    -- Error container
    local ErrorContainer = Instance.new("Frame")
    ErrorContainer.Size = UDim2.new(0, 400, 0, 250)
    ErrorContainer.Position = UDim2.new(0.5, -200, 0.5, -125)
    ErrorContainer.BackgroundColor3 = Color3.fromRGB(30, 30, 30)
    ErrorContainer.BorderSizePixel = 0
    ErrorContainer.Parent = ErrorGui
    
    local Corner = Instance.new("UICorner")
    Corner.CornerRadius = UDim.new(0, 15)
    Corner.Parent = ErrorContainer
    
    local Stroke = Instance.new("UIStroke")
    Stroke.Color = Color3.fromRGB(255, 50, 50)
    Stroke.Thickness = 2
    Stroke.Parent = ErrorContainer
    
    -- Title
    local TitleLabel = Instance.new("TextLabel")
    TitleLabel.Size = UDim2.new(1, 0, 0, 60)
    TitleLabel.BackgroundColor3 = Color3.fromRGB(40, 20, 20)
    TitleLabel.BorderSizePixel = 0
    TitleLabel.Font = Enum.Font.GothamBold
    TitleLabel.Text = "❌ ACCESS DENIED"
    TitleLabel.TextColor3 = Color3.fromRGB(255, 100, 100)
    TitleLabel.TextSize = 18
    TitleLabel.Parent = ErrorContainer
    
    local TitleCorner = Instance.new("UICorner")
    TitleCorner.CornerRadius = UDim.new(0, 15)
    TitleCorner.Parent = TitleLabel
    
    -- Error message
    local MessageLabel = Instance.new("TextLabel")
    MessageLabel.Size = UDim2.new(1, -20, 0, 80)
    MessageLabel.Position = UDim2.new(0, 10, 0, 70)
    MessageLabel.BackgroundTransparency = 1
    MessageLabel.Font = Enum.Font.Gotham
    MessageLabel.Text = errorMessage
    MessageLabel.TextColor3 = Color3.fromRGB(255, 150, 150)
    MessageLabel.TextSize = 14
    MessageLabel.TextWrapped = true
    MessageLabel.TextXAlignment = Enum.TextXAlignment.Center
    MessageLabel.TextYAlignment = Enum.TextYAlignment.Top
    MessageLabel.Parent = ErrorContainer
    
    -- Leave button
    local LeaveButton = Instance.new("TextButton")
    LeaveButton.Size = UDim2.new(0, 150, 0, 40)
    LeaveButton.Position = UDim2.new(0.5, -75, 1, -50)
    LeaveButton.BackgroundColor3 = Color3.fromRGB(200, 50, 50)
    LeaveButton.BorderSizePixel = 0
    LeaveButton.Font = Enum.Font.GothamBold
    LeaveButton.Text = "Leave Game"
    LeaveButton.TextColor3 = Color3.fromRGB(255, 255, 255)
    LeaveButton.TextSize = 14
    LeaveButton.Parent = ErrorContainer
    
    local ButtonCorner = Instance.new("UICorner")
    ButtonCorner.CornerRadius = UDim.new(0, 8)
    ButtonCorner.Parent = LeaveButton
    
    -- Button hover effect
    LeaveButton.MouseEnter:Connect(function()
        LeaveButton.BackgroundColor3 = Color3.fromRGB(220, 80, 80)
    end)
    
    LeaveButton.MouseLeave:Connect(function()
        LeaveButton.BackgroundColor3 = Color3.fromRGB(200, 50, 50)
    end)
    
    -- Leave game on click
    LeaveButton.MouseButton1Click:Connect(function()
        Players:LeaveGame()
    end)
end

-- Validate key sa server
local function validateKey(k)
    local requestBody = '{"key":"' .. k .. '"}'
    
    local success, response = pcall(function()
        return game:HttpPost(
            validationURL,
            requestBody,
            Enum.HttpContentType.ApplicationJson,
            true
        )
    end)
    
    if not success then
        warn("❌ Validation error: " .. tostring(response))
        showErrorScreen("Validation Server Error\n\n" .. tostring(response))
        return false
    end
    
    -- Check if response contains "valid":true
    if response and string.find(response, '"valid"%s*:%s*true') then
        print("✅ Key validated successfully!")
        return true
    else
        warn("❌ Invalid or expired key")
        print("Response: " .. tostring(response))
        return false
    end
end

if not validateKey(key) then
    warn("🚫 Access denied. Script will not load.")
    showErrorScreen("Invalid or Expired Key\n\nYour key is either invalid, already used, or has expired.\n\nPlease request a new key from the administrator.")
    return
end

print("✅ Key validation passed! Loading main script...")

-- ========================================
-- 🚀 MAIN HUB (YOUR ORIGINAL SCRIPT)
-- ========================================

-- // [1] SERVICES //
local Players = game:GetService("Players")
local CoreGui = game:GetService("CoreGui")
local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local LocalPlayer = Players.LocalPlayer

-- // [2] CONFIGURATION //
local CONFIG = {
    Names = {
        ScreenGui = "Space Anti Bat",
        MainFrame = "MainFrame",
        TitleLabel = "TitleLabel",
        ContentFrame = "ContentFrame",
        Prefix = "Feature_"
    },

    Size = {
        MainFrame = UDim2.new(0, 240, 0, 210),
        TitleFrame = UDim2.new(1, 0, 0, 40),
        ContentFrame = UDim2.new(1, -20, 1, -55),
        Button = UDim2.new(1, 0, 0, 40),
        RowFrame = UDim2.new(1, 0, 0, 30),
        BindButton = UDim2.new(0, 70, 1, 0)
    },

    Position = {
        MainFrame = UDim2.new(0.5, -120, 0.5, -135),
        TitleLabel = UDim2.new(0, 15, 0, 0),
        ContentFrame = UDim2.new(0, 10, 0, 45),
        BindButton = UDim2.new(0.6, 0, 0, 0)
    },

    Colors = {
        Background = Color3.fromRGB(0, 0, 0),
        ButtonBg = Color3.fromRGB(20, 20, 20),
        BindBg = Color3.fromRGB(30, 30, 30),
        Border = Color3.fromRGB(80, 80, 80),
        TextPrimary = Color3.fromRGB(255, 255, 255),
        TextSecondary = Color3.fromRGB(200, 200, 200),
        TextMuted = Color3.fromRGB(150, 150, 150),
        AccentOn = Color3.fromRGB(0, 255, 0)
    },

    Font = Enum.Font.GothamBold,
    MutedFont = Enum.Font.Gotham,
    BackgroundTransparency = 0.3,
    
    Toggles = {
        AntiBat = true,
        InfJump = true
    },
    
    ToggleKey = Enum.KeyCode.V
}

-- // [3] OBJECT REFERENCES //
local ScreenGui
local MainFrame
local TitleFrame
local TitleLabel
local ContentFrame
local UIListLayout
local AntiBatButton
local InfJumpButton
local BindRowFrame
local BindLabel
local BindButton
local InfoLabel

local BackgroundImage
local MainCorner
local MainStroke
local Button1Corner
local Button1Stroke
local Button2Corner
local Button2Stroke
local BindCorner

-- // [4] UTILITY FUNCTIONS //
local function getHRP()
    local character = LocalPlayer.Character
    if not character then return nil end
    return character:FindFirstChild("HumanoidRootPart")
end

-- // [5] GUI CREATION //
local function createGUI()
    ScreenGui = Instance.new("ScreenGui")
    ScreenGui.Name = CONFIG.Names.ScreenGui
    ScreenGui.ResetOnSpawn = false
    ScreenGui.Parent = CoreGui

    MainFrame = Instance.new("Frame")
    MainFrame.Name = CONFIG.Names.MainFrame
    MainFrame.BackgroundColor3 = CONFIG.Colors.Background
    MainFrame.BackgroundTransparency = CONFIG.BackgroundTransparency
    MainFrame.Position = CONFIG.Position.MainFrame
    MainFrame.Size = CONFIG.Size.MainFrame
    MainFrame.ClipsDescendants = true
    MainFrame.Active = true
    MainFrame.Draggable = true
    MainFrame.Parent = ScreenGui

    MainCorner = Instance.new("UICorner")
    MainCorner.CornerRadius = UDim.new(0, 10)
    MainCorner.Parent = MainFrame

    MainStroke = Instance.new("UIStroke")
    MainStroke.Color = CONFIG.Colors.Border
    MainStroke.Thickness = 1.5
    MainStroke.Parent = MainFrame

    BackgroundImage = Instance.new("ImageLabel")
    BackgroundImage.Size = UDim2.new(1, 0, 1, 0)
    BackgroundImage.Image = "rbxassetid://118100574986629"
    BackgroundImage.ScaleType = Enum.ScaleType.Crop
    BackgroundImage.BackgroundTransparency = 1
    BackgroundImage.ZIndex = 0
    BackgroundImage.Parent = MainFrame

    TitleFrame = Instance.new("Frame")
    TitleFrame.BackgroundTransparency = 1
    TitleFrame.Size = CONFIG.Size.TitleFrame
    TitleFrame.ZIndex = 2
    TitleFrame.Parent = MainFrame

    TitleLabel = Instance.new("TextLabel")
    TitleLabel.Name = CONFIG.Names.TitleLabel
    TitleLabel.BackgroundTransparency = 1
    TitleLabel.Position = CONFIG.Position.TitleLabel
    TitleLabel.Size = UDim2.new(1, -30, 1, 0)
    TitleLabel.Font = CONFIG.Font
    TitleLabel.Text = "Space Hub"
    TitleLabel.TextColor3 = CONFIG.Colors.TextPrimary
    TitleLabel.TextSize = 14
    TitleLabel.TextXAlignment = Enum.TextXAlignment.Left
    TitleLabel.ZIndex = 2
    TitleLabel.Parent = TitleFrame

    ContentFrame = Instance.new("Frame")
    ContentFrame.Name = CONFIG.Names.ContentFrame
    ContentFrame.Position = CONFIG.Position.ContentFrame
    ContentFrame.Size = CONFIG.Size.ContentFrame
    ContentFrame.BackgroundTransparency = 1
    ContentFrame.Parent = MainFrame

    UIListLayout = Instance.new("UIListLayout")
    UIListLayout.SortOrder = Enum.SortOrder.LayoutOrder
    UIListLayout.Padding = UDim.new(0, 8)
    UIListLayout.Parent = ContentFrame

    AntiBatButton = Instance.new("TextButton")
    AntiBatButton.Name = CONFIG.Names.Prefix .. "AntiBat"
    AntiBatButton.Size = CONFIG.Size.Button
    AntiBatButton.BackgroundColor3 = CONFIG.Colors.ButtonBg
    AntiBatButton.BackgroundTransparency = 0.2
    AntiBatButton.BorderSizePixel = 0
    AntiBatButton.Font = CONFIG.Font
    AntiBatButton.TextSize = 14
    AntiBatButton.AutoButtonColor = false
    AntiBatButton.Parent = ContentFrame

    Button1Corner = Instance.new("UICorner")
    Button1Corner.CornerRadius = UDim.new(0, 8)
    Button1Corner.Parent = AntiBatButton

    Button1Stroke = Instance.new("UIStroke")
    Button1Stroke.Thickness = 1
    Button1Stroke.Parent = AntiBatButton

    InfJumpButton = Instance.new("TextButton")
    InfJumpButton.Name = CONFIG.Names.Prefix .. "InfJump"
    InfJumpButton.Size = CONFIG.Size.Button
    InfJumpButton.BackgroundColor3 = CONFIG.Colors.ButtonBg
    InfJumpButton.BackgroundTransparency = 0.2
    InfJumpButton.BorderSizePixel = 0
    InfJumpButton.Font = CONFIG.Font
    InfJumpButton.TextSize = 14
    InfJumpButton.AutoButtonColor = false
    InfJumpButton.Parent = ContentFrame

    Button2Corner = Instance.new("UICorner")
    Button2Corner.CornerRadius = UDim.new(0, 8)
    Button2Corner.Parent = InfJumpButton

    Button2Stroke = Instance.new("UIStroke")
    Button2Stroke.Thickness = 1
    Button2Stroke.Parent = InfJumpButton

    BindRowFrame = Instance.new("Frame")
    BindRowFrame.Size = CONFIG.Size.RowFrame
    BindRowFrame.BackgroundTransparency = 1
    BindRowFrame.Parent = ContentFrame

    BindLabel = Instance.new("TextLabel")
    BindLabel.Size = UDim2.new(0.5, 0, 1, 0)
    BindLabel.Font = CONFIG.MutedFont
    BindLabel.Text = "Toggle Keybind:"
    BindLabel.TextColor3 = CONFIG.Colors.TextSecondary
    BindLabel.TextSize = 12
    BindLabel.BackgroundTransparency = 1
    BindLabel.TextXAlignment = Enum.TextXAlignment.Left
    BindLabel.Parent = BindRowFrame

    BindButton = Instance.new("TextButton")
    BindButton.Position = CONFIG.Position.BindButton
    BindButton.Size = CONFIG.Size.BindButton
    BindButton.BackgroundColor3 = CONFIG.Colors.BindBg
    BindButton.BorderSizePixel = 0
    BindButton.Font = CONFIG.Font
    BindButton.Text = CONFIG.ToggleKey.Name
    BindButton.TextColor3 = CONFIG.Colors.TextPrimary
    BindButton.TextSize = 12
    BindButton.Parent = BindRowFrame

    BindCorner = Instance.new("UICorner")
    BindCorner.CornerRadius = UDim.new(0, 5)
    BindCorner.Parent = BindButton

    InfoLabel = Instance.new("TextLabel")
    InfoLabel.Size = UDim2.new(1, 0, 0, 20)
    InfoLabel.BackgroundTransparency = 1
    InfoLabel.Font = CONFIG.MutedFont
    InfoLabel.Text = "Anti-Bat | Power: 4000 | Inf Jump"
    InfoLabel.TextColor3 = CONFIG.Colors.TextMuted
    InfoLabel.TextSize = 10
    InfoLabel.Parent = ContentFrame
end

-- // [6] FUNCTIONALITY //
local function updateVisuals()
    if CONFIG.Toggles.AntiBat then
        AntiBatButton.Text = "Anti-Bat : ON"
        AntiBatButton.TextColor3 = CONFIG.Colors.AccentOn
        Button1Stroke.Color = CONFIG.Colors.AccentOn
    else
        AntiBatButton.Text = "Anti-Bat : OFF"
        AntiBatButton.TextColor3 = CONFIG.Colors.TextPrimary
        Button1Stroke.Color = CONFIG.Colors.Border
    end

    if CONFIG.Toggles.InfJump then
        InfJumpButton.Text = "Inf Jump : ON"
        InfJumpButton.TextColor3 = CONFIG.Colors.AccentOn
        Button2Stroke.Color = CONFIG.Colors.AccentOn
    else
        InfJumpButton.Text = "Inf Jump : OFF"
        InfJumpButton.TextColor3 = CONFIG.Colors.TextPrimary
        Button2Stroke.Color = CONFIG.Colors.Border
    end
end

local function setupLogic()
    AntiBatButton.MouseButton1Click:Connect(function()
        CONFIG.Toggles.AntiBat = not CONFIG.Toggles.AntiBat
        updateVisuals()
    end)

    InfJumpButton.MouseButton1Click:Connect(function()
        CONFIG.Toggles.InfJump = not CONFIG.Toggles.InfJump
        updateVisuals()
    end)

    UserInputService.InputBegan:Connect(function(input, processed)
        if processed then return end
        if input.KeyCode == CONFIG.ToggleKey then
            ScreenGui.Enabled = not ScreenGui.Enabled
        end
    end)

    -- Infinite Jump Logic
    UserInputService.JumpRequest:Connect(function()
        if CONFIG.Toggles.InfJump then
            local hrp = getHRP()
            if hrp then
                hrp.Velocity = Vector3.new(hrp.Velocity.X, 40, hrp.Velocity.Z)
            end
        end
    end)

    -- Anti-Bat Logic
    RunService.PostSimulation:Connect(function()
        if CONFIG.Toggles.AntiBat then
            local hrp = getHRP()
            if hrp then
                for _, child in ipairs(hrp:GetChildren()) do
                    if child:IsA("BodyVelocity") or child:IsA("BodyGyro") then
                        child:Destroy()
                    elseif child:IsA("Velocity") then
                        pcall(function() child:Destroy() end)
                    end
                end
            end
        end
    end)
end

-- // [7] INITIALIZATION //
createGUI()
updateVisuals()
setupLogic()
