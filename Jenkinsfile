pipeline {
  agent any

  // No parameters{} required. If you use "This project is parameterized",
  // Jenkins exposes values as params.* and env.* automatically.

    parameters {
        string(name: 'DEVICE', defaultValue: '', description: 'Serial/IP or IP:port of target device')
    }
  environment {
    SEVEN_ZIP = ''   // we will auto-detect at runtime if empty
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

    stage('Prep workspace dirs') {
      steps {
        script {
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
        }
      }
    }

    stage('Write runtime config (SAFE)') {
      steps {
        script {
          // Prefer env (Configure → Build Environment or Parameter defaults), then params
          def dev    = (env.DEVICE ?: params.DEVICE ?: '').trim()
          def auth   = (env.AUTH   ?: params.AUTH   ?: '')
          def cookie = (env.COOKIE ?: params.COOKIE ?: '')

          if (!dev) {
            error "DEVICE is empty. Set it in Configure (either as ENV under Build Environment or as a String Parameter default)."
          }

          writeFile file: 'config/devices.txt', text: dev
          writeFile file: 'config/auth.txt',    text: auth
          writeFile file: 'config/cookie.txt',  text: cookie

          echo "DEVICE='${dev}'"   // non-secret; helpful to confirm in Console Output
        }
      }
    }

    stage('Run tests') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -e
              export REPORTS_DIR="$WORKSPACE/reports/$BUILD_NUMBER"
              export REPORT_FILE="index.html"
              mkdir -p "$REPORTS_DIR"

              # mac/Linux 7-Zip detect
              export SEVEN_ZIP="${SEVEN_ZIP:-$(command -v 7zz || command -v 7z || true)}"
              echo "SEVEN_ZIP=${SEVEN_ZIP:-<none>}"

              . .venv/bin/activate
              python3 tests_run.py
            '''
          } else {
            bat '''
              setlocal EnableDelayedExpansion
              set "REPORTS_DIR=%WORKSPACE%\\reports\\%BUILD_NUMBER%"
              set "REPORT_FILE=index.html"
              if not exist "%REPORTS_DIR%" mkdir "%REPORTS_DIR%"

              rem Robust 7-Zip auto-detect
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
      junit allowEmptyResults: true, testResults: 'reports/${env.BUILD_NUMBER}/**/*.xml'

      publishHTML(target: [
        reportDir: "reports/${env.BUILD_NUMBER}",
        reportFiles: "index.html",
        reportName: "Report #${env.BUILD_NUMBER}",
        keepAll: true,
        allowMissing: false,
        alwaysLinkToLastBuild: false
      ])
      archiveArtifacts artifacts: "reports/${env.BUILD_NUMBER}/**/*.html, downloaded_bugreports/**/*.zip, **/debugarchive_*.zip",
                   fingerprint: true, onlyIfSuccessful: false


    }
  }
}