pipeline {
  agent { label 'windows' }        // your Windows agent label

  parameters {
    // Paste the file contents here each run (or set defaults in job config)
    text(name: 'AUTH_TXT',   defaultValue: '', description: 'Contents of auth.txt')
    text(name: 'COOKIE_TXT', defaultValue: '', description: 'Contents of cookie.txt')

    // Devices are provided ONLY via Jenkins params (no repo JSON)
    string(name: 'DEVICES',
           defaultValue: '',
           description: 'Comma/space/semicolon separated IPs. :5555 is added if missing')

    choice(name: 'TEST_TARGET',
           choices: ['auto','tests_mtr','tests_zoom','tests_device_mode','tests_oobe','tests_scripts'],
           description: 'Which suite to run. "auto" selects by focused app.')

    booleanParam(name: 'RUN_IN_PARALLEL', defaultValue: false,
                 description: 'Run one branch per device')

    string(name: 'SEVEN_ZIP_PATH',
           defaultValue: 'C:\\Program Files\\7-Zip\\7z.exe',
           description: 'Full path to 7-Zip on the agent')
  }

  environment {
    // convenience for Windows venv
    VENV_ACT = ".venv\\Scripts\\activate.bat"
    PYTHON   = ".venv\\Scripts\\python.exe"
    PIP      = ".venv\\Scripts\\pip.exe"

    // pass-throughs your Python uses
    DEVICES    = "${params.DEVICES}"
    TEST_TARGET= "${params.TEST_TARGET}"
    SEVEN_ZIP  = "${params.SEVEN_ZIP_PATH}"
  }

  stages {
    stage('Checkout') {
      steps {
        bat 'git config --global core.longpaths true'    // avoids long path errors on Windows
        checkout scm
      }
    }

    stage('Python Setup') {
      steps {
        bat """
          if not exist .venv ( py -3 -m venv .venv )
          call ${VENV_ACT} && python -m pip install --upgrade pip
          call ${VENV_ACT} && pip install -r requirements.txt
        """
      }
    }

    stage('Write runtime config from params') {
      steps {
        // never echo these to console
        bat 'if not exist config mkdir config'
        writeFile file: 'config/auth.txt',   text: params.AUTH_TXT
        writeFile file: 'config/cookie.txt', text: params.COOKIE_TXT
      }
    }

    stage('Run tests (serial)') {
      when { expression { !params.RUN_IN_PARALLEL } }
      steps {
        bat """
          call ${VENV_ACT} ^
          && set DEVICES=${DEVICES} ^
          && set TEST_TARGET=${TEST_TARGET} ^
          && set SEVEN_ZIP=${SEVEN_ZIP} ^
          && ${PYTHON} tests_run.py
        """
      }
    }

    stage('Run tests (parallel by device)') {
      when { expression { params.RUN_IN_PARALLEL } }
      steps {
        script {
          def ips = params.DEVICES.split(/[\\s,;]+/) as List
          ips = ips.findAll { it?.trim() }.collect { it.contains(':') ? it.trim() : it.trim() + ':5555' }

          def branches = [:]
          ips.eachWithIndex { ip, i ->
            branches["device-${i}-${ip}"] = {
              // same node/agent so workspaces share the repo (simple and fast)
              bat "call ${VENV_ACT} || (py -3 -m venv .venv && call ${VENV_ACT} && pip install -r requirements.txt)"
              bat 'if not exist config mkdir config'
              writeFile file: 'config/auth.txt',   text: params.AUTH_TXT
              writeFile file: 'config/cookie.txt', text: params.COOKIE_TXT
              bat """
                call ${VENV_ACT} ^
                && set DEVICES=${ip} ^
                && set TEST_TARGET=${params.TEST_TARGET} ^
                && set SEVEN_ZIP=${params.SEVEN_ZIP_PATH} ^
                && ${PYTHON} tests_run.py
              """
            }
          }
          parallel branches
        }
      }
    }

    stage('Archive reports/artifacts') {
      steps {
        archiveArtifacts artifacts: 'reports/**/*.html, downloaded_bugreports/**, extracted_bugreports/**',
                         allowEmptyArchive: true
      }
    }
  }

  post {
    success { echo '✅ Build finished OK' }
    failure { echo '❌ Build failed—see Console Output for the first error.' }
    always  { junit allowEmptyResults: true, testResults: 'reports/**/*.xml' }
  }
}