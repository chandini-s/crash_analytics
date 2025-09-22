pipeline {
  // Change if you want to pin to a node label (e.g., 'mac-mini' or 'windows-local')
  agent any
  options { timestamps(); ansiColor('xterm') }

  // No `parameters {}` on purpose — values come from job Configure → Build Environment → Environment variables
  // Add there: DEVICE, AUTH, COOKIE

  environment {
    SEVEN_ZIP = ''  // auto-detect per-OS below
  }

  stages {
    stage('Checkout') { steps { checkout scm } }

    stage('Python venv & deps') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -euo pipefail
              python3 -m venv .venv
              . .venv/bin/activate
              python -m pip install --upgrade pip
              if [ -f requirements.txt ]; then
                pip install -r requirements.txt
              else
                pip install pytest pytest-html requests
              fi
            '''
          } else {
            bat '''
              if not exist .venv\\Scripts\\python.exe ( py -3 -m venv .venv )
              .venv\\Scripts\\python.exe -m pip install --upgrade pip
              if exist requirements.txt (
                .venv\\Scripts\\pip.exe install -r requirements.txt
              ) else (
                .venv\\Scripts\\pip.exe install pytest pytest-html requests
              )
            '''
          }
        }
      }
    }

    stage('Prep workspace dirs + config (from ENV)') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -e
              rm -rf "$WORKSPACE/reports" "$WORKSPACE/downloaded_bugreports" "$WORKSPACE/config"
              mkdir -p "$WORKSPACE/reports" "$WORKSPACE/downloaded_bugreports" "$WORKSPACE/config"

              # Write ENV values to files (your utils can read env first, then these files as fallback)
              printf "%s" "${AUTH:-}"   > "$WORKSPACE/config/auth.txt"
              printf "%s" "${COOKIE:-}" > "$WORKSPACE/config/cookie.txt"
              printf "%s" "${DEVICE:-}" > "$WORKSPACE/config/devices.txt"
            '''
          } else {
            bat """
              if exist "%WORKSPACE%\\reports" rmdir /s /q "%WORKSPACE%\\reports"
              if exist "%WORKSPACE%\\downloaded_bugreports" rmdir /s /q "%WORKSPACE%\\downloaded_bugreports"
              if exist "%WORKSPACE%\\config" rmdir /s /q "%WORKSPACE%\\config"
              mkdir "%WORKSPACE%\\reports" "%WORKSPACE%\\downloaded_bugreports" "%WORKSPACE%\\config"

              call :WRITE "%WORKSPACE%\\config\\auth.txt" "%%AUTH%%"
              call :WRITE "%WORKSPACE%\\config\\cookie.txt" "%%COOKIE%%"
              call :WRITE "%WORKSPACE%\\config\\devices.txt" "%%DEVICE%%"
              goto :NEXT
              :WRITE
              > %~1 (echo|set /p=%~2)
              exit /b 0
              :NEXT
            """
          }
        }
      }
    }

    stage('Run tests (focused app decides)') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -e
              : "${DEVICE:?Set DEVICE in job Configure → Build Environment → Environment variables}"

              export DEVICE="${DEVICE}"
              export REPORTS_DIR="$WORKSPACE/reports"   # Python writes here
              export REPORT_FILE="index.html"           # single stable filename

              # Find 7-Zip if available (Homebrew p7zip installs 7zz)
              export SEVEN_ZIP="${SEVEN_ZIP:-$(command -v 7zz || command -v 7z || true)}"

              . .venv/bin/activate
              python3 tests_run.py
            '''
          } else {
            bat """
              if "%%DEVICE%%"=="" (
                echo ERROR: Set DEVICE under Configure ^> Build Environment ^> Environment variables & exit /b 2
              )
              set REPORTS_DIR=%WORKSPACE%\\reports
              set REPORT_FILE=index.html
              if not exist "%%REPORTS_DIR%%" mkdir "%%REPORTS_DIR%%"

              rem Auto-detect 7-Zip if not provided
              if "%%SEVEN_ZIP%%"=="" (
                if exist "%%ProgramFiles%%\\7-Zip\\7z.exe" set SEVEN_ZIP=%%ProgramFiles%%\\7-Zip\\7z.exe
                if exist "%%ProgramFiles(x86)%%\\7-Zip\\7z.exe" set SEVEN_ZIP=%%ProgramFiles(x86)%%\\7-Zip\\7z.exe
              )

              .venv\\Scripts\\python.exe tests_run.py
              if errorlevel 1 exit /b 1
            """
          }
        }
      }
    }
  }

  post {
    always {
      junit allowEmptyResults: true, testResults: 'reports/**/*.xml'
      archiveArtifacts artifacts: 'reports/*.html, downloaded_bugreports/**/*.zip, **/debugarchive_*.zip',
                       fingerprint: true, onlyIfSuccessful: false
      script {
        catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
          publishHTML(target: [
            reportDir: 'reports',
            reportFiles: 'index.html',
            reportName: 'Crash Analytics – Latest HTML Report',
            keepAll: true, allowMissing: true, alwaysLinkToLastBuild: true
          ])
        }
      }
    }
  }
}
