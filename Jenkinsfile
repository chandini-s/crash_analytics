pipeline {
  // Change to a label if you want to pin to a node (e.g. 'mac-mini' or 'windows-local')
  agent any

  // No `parameters {}` on purpose. Set DEVICE/AUTH/COOKIE in:
  // Job → Configure → Build Environment → Environment variables
  environment {
    SEVEN_ZIP = ''   // we will auto-detect per-OS at runtime if this is empty
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
        // Write files using Jenkins, not shell, to avoid quoting/expansion issues
        script {
          // prefer env.* (Configure), fall back to params.* if present
          def dev    = (env.DEVICE ?: params.DEVICE ?: '')
          def auth   = (env.AUTH   ?: params.AUTH   ?: '')
          def cookie = (env.COOKIE ?: params.COOKIE ?: '')

          // fail fast if required input missing
          if (!dev) {
            error "DEVICE is empty. Set it in Job → Configure → Build Environment → Environment variables."
          }

          // recreate dirs
          if (isUnix()) {
            sh 'rm -rf "$WORKSPACE/reports" "$WORKSPACE/downloaded_bugreports" "$WORKSPACE/config" && mkdir -p "$WORKSPACE/reports" "$WORKSPACE/downloaded_bugreports" "$WORKSPACE/config"'
          } else {
            bat '''
              if exist "%WORKSPACE%\\reports" rmdir /s /q "%WORKSPACE%\\reports"
              if exist "%WORKSPACE%\\downloaded_bugreports" rmdir /s /q "%WORKSPACE%\\downloaded_bugreports"
              if exist "%WORKSPACE%\\config" rmdir /s /q "%WORKSPACE%\\config"
              mkdir "%WORKSPACE%\\reports" "%WORKSPACE%\\downloaded_bugreports" "%WORKSPACE%\\config"
            '''
          }

          // write runtime config files
          writeFile file: 'config/devices.txt', text: dev
          writeFile file: 'config/auth.txt',    text: auth
          writeFile file: 'config/cookie.txt',  text: cookie
        }
      }
    }

    stage('Run tests (focused app decides)') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -e
              export DEVICE="${DEVICE}"
              export REPORTS_DIR="$WORKSPACE/reports"
              export REPORT_FILE="index.html"
              mkdir -p "$REPORTS_DIR"

              # Robust 7-Zip detect on mac/Linux
              export SEVEN_ZIP="${SEVEN_ZIP:-$(command -v 7zz || command -v 7z || true)}"
              echo "SEVEN_ZIP=${SEVEN_ZIP:-<none>}   DEVICE=${DEVICE}   REPORTS_DIR=$REPORTS_DIR"

              . .venv/bin/activate
              python3 tests_run.py
            '''
          } else {
            bat '''
              setlocal EnableDelayedExpansion

              set "REPORTS_DIR=%WORKSPACE%\\reports"
              set "REPORT_FILE=index.html"
              if not exist "%REPORTS_DIR%" mkdir "%REPORTS_DIR%"

              rem ===== Robust 7-Zip auto-detect (no ProgramFiles parsing) =====
              if "%SEVEN_ZIP%"=="" (
                for /f "usebackq delims=" %%P in (`where 7z.exe 2^>nul`) do set "SEVEN_ZIP=%%P"
                if not defined SEVEN_ZIP for /f "usebackq delims=" %%P in (`where 7zz.exe 2^>nul`) do set "SEVEN_ZIP=%%P"
              )
              echo SEVEN_ZIP=%SEVEN_ZIP%

              .venv\\Scripts\\python.exe tests_run.py
              if errorlevel 1 exit /b 1
            '''
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
      // Publish the single stable HTML file we wrote (reports/index.html)
      script {
        catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
          publishHTML(target: [
            reportDir: 'reports',
            reportFiles: 'index.html',
            reportName: 'Crash Analytics – Latest HTML Report',
            keepAll: true,
            allowMissing: true,
            alwaysLinkToLastBuild: true
          ])
        }
      }
    }
  }
}