{
  description = "herdr-kitten — herdr IS the kitty kitten: one Python kitten + one stdlib CLI making herdr the transport layer under kitty";

  inputs = {
    # Pinned to the census/source-of-record rev (v0.8.2, wire protocol 21).
    # Upstream org/tag verified 2026-09-01 via the GitHub API: herdrdev/herdr,
    # tag v0.8.2 exists, and this rev is reachable on master.
    herdr.url = "github:herdrdev/herdr/dbc398f580d1da6c336c6837a60b7e0710501d6d";
    nixpkgs.follows = "herdr/nixpkgs";
  };

  outputs = { self, nixpkgs, herdr }:
    let
      lib = nixpkgs.lib;
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = lib.genAttrs systems;
    in
    {
      packages = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in rec {
          herdr-kitten = pkgs.stdenv.mkDerivation {
            pname = "herdr-kitten";
            version = "0.1.0-dev";
            src = ./.;
            buildInputs = [ pkgs.python3 ];
            installPhase = ''
              runHook preInstall
              mkdir -p $out/bin $out/share/hk/bin
              cp -R hk kitten assets conf $out/share/hk/
              install -Dm755 bin/hk $out/share/hk/bin/hk
              # bin/hk resolves the hk package via ../hk of its realpath, so the
              # public entry point is a symlink into the share tree.
              ln -s $out/share/hk/bin/hk $out/bin/hk
              runHook postInstall
            '';
            meta.mainProgram = "hk";
          };
          default = herdr-kitten;
        });

      checks = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          herdrPkg = herdr.packages.${system}.default;
        in {
          # D27 half 1: artifacts compile, imports are stdlib-only, units pass.
          herdr-kitten-build = pkgs.runCommand "herdr-kitten-build"
            {
              src = ./.;
              # kitty is a TEST dependency, not a runtime one: tests/unit/
              # test_kitten.py drives kitten/hk.py through the real
              # kittens.runner loader. Without it that gate would SKIP, and a
              # skipped loader gate is exactly how BUG-1/BUG-2 shipped, so
              # HK_REQUIRE_KITTY=1 below turns a missing kitty into a failure.
              nativeBuildInputs = [ pkgs.python3 pkgs.kitty ];
              HK_REQUIRE_KITTY = "1";
            } ''
            cp -R --no-preserve=mode "$src" source
            cd source
            python3 -m py_compile bin/hk kitten/hk.py hk/*.py
            PYTHONPATH=. python3 -m unittest discover -s tests/unit -v
            # the shipped package really runs
            python3 bin/hk --version
            touch $out
          '';

          # D27 half 2: headless smoke battery against a LIVE herdr server in a
          # sandbox HOME (kitty-attended gates run on the executor's machine,
          # never here — spec D27/G18).
          herdr-kitten-smoke = pkgs.runCommand "herdr-kitten-smoke"
            { src = ./.; nativeBuildInputs = [ pkgs.python3 pkgs.git herdrPkg ]; } ''
            cp -R --no-preserve=mode "$src" source
            cd source
            chmod +x bin/hk tests/smoke/*.sh install.sh
            export PATH="$PWD/bin:$PATH"
            sh tests/smoke/run-headless.sh 2>&1 | tee $out
          '';
        });
    };
}
