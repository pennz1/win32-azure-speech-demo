; ============================================================
; Azure AI 语音演示台 — NSIS 安装脚本
; 生成命令: makensis installer.nsi
; 前置条件: dist\AzureAISpeechDemo.exe 已由 PyInstaller 构建
; ============================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; ── 产品信息 ──────────────────────────────────────────────────
!define PRODUCT_NAME    "领驭科技 Azure AI 语音演示台"
!define PRODUCT_EXE     "AzureAISpeechDemo.exe"
; PRODUCT_VERSION 可由构建脚本通过 /DPRODUCT_VERSION=x.x.x 传入，当前默认为下方备用值
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "2.0.0322.12"
!endif
!define PUBLISHER       "领驭科技-技术组"
!define UNINST_KEY      "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\AzureAISpeechDemo_Setup_${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin

; ── 图标（如果有 app.ico 就使用，否则注释掉这两行）─────────
; 将你的 app.ico 放在项目根目录，取消下面两行注释即可
!define MUI_ICON "app.ico"
!define MUI_UNICON "app.ico"

; ── 安装向导页面 ──────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${PRODUCT_NAME}"
!define MUI_WELCOMEPAGE_TEXT "本向导将引导您完成 ${PRODUCT_NAME} ${PRODUCT_VERSION} 的安装。$\r$\n$\r$\n运行本程序需要：$\r$\n  - Microsoft Visual C++ Redistributable (x64)$\r$\n$\r$\n点击「下一步」继续。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${PRODUCT_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即运行 ${PRODUCT_NAME}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; ── 卸载向导页面 ──────────────────────────────────────────────
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; ── 语言 ──────────────────────────────────────────────────────
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ============================================================
; 安装区段
; ============================================================
Section "主程序" SEC_MAIN
    SectionIn RO ; 必选

    ; 强制结束正在运行的旧版本（避免 EXE 被锁定无法覆盖）
    nsExec::Exec 'taskkill /F /IM "${PRODUCT_EXE}"'
    Sleep 1500

    SetOutPath "$INSTDIR"
    SetOverwrite on

    ; 复制主程序
    File "dist\${PRODUCT_EXE}"

    ; 如果有 ICO 图标文件，取消下行注释
    File "app.ico"

    ; ── 创建开始菜单快捷方式 ──────────────────────────────────
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" \
        "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\卸载 ${PRODUCT_NAME}.lnk" \
        "$INSTDIR\Uninstall.exe"

    ; ── 桌面快捷方式 ─────────────────────────────────────────
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" \
        "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0

    ; ── 写入卸载注册表 ───────────────────────────────────────
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr HKLM "${UNINST_KEY}" "DisplayName"     "${PRODUCT_NAME}"
    WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion"  "${PRODUCT_VERSION}"
    WriteRegStr HKLM "${UNINST_KEY}" "Publisher"        "${PUBLISHER}"
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1

    ; 计算安装大小
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" $0
SectionEnd

; ── VC++ 运行库检查（安装后提示）──────────────────────────────
Section "-CheckVCRedist"
    ; 检查 VCRUNTIME140.dll 是否存在
    IfFileExists "$SYSDIR\VCRUNTIME140.dll" vcredist_ok vcredist_missing

    vcredist_missing:
        MessageBox MB_YESNO|MB_ICONEXCLAMATION \
            "检测到系统缺少 Microsoft Visual C++ Redistributable (x64)。$\r$\n$\r$\n\
            程序运行需要此组件。是否打开下载页面？$\r$\n$\r$\n\
            下载地址: https://aka.ms/vs/17/release/vc_redist.x64.exe" \
            IDYES open_vcredist IDNO vcredist_ok

    open_vcredist:
        ExecShell "open" "https://aka.ms/vs/17/release/vc_redist.x64.exe"

    vcredist_ok:
SectionEnd

; ============================================================
; 卸载区段
; ============================================================
Section "Uninstall"
    ; 结束正在运行的程序再删除
    nsExec::Exec 'taskkill /F /IM "${PRODUCT_EXE}"'
    Sleep 1000

    ; 删除程序文件
    Delete "$INSTDIR\${PRODUCT_EXE}"
    Delete "$INSTDIR\Uninstall.exe"
    Delete "$INSTDIR\app.ico"  ; 如果安装了图标，取消此行注释
    RMDir "$INSTDIR"

    ; 删除开始菜单
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\卸载 ${PRODUCT_NAME}.lnk"
    RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

    ; 删除桌面快捷方式
    Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

    ; 删除注册表
    DeleteRegKey HKLM "${UNINST_KEY}"

    ; 注意：不删除用户配置目录 (~/.azure_ai_demo)，保留用户数据
SectionEnd
