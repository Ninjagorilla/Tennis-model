import test from 'node:test';
import assert from 'node:assert/strict';
import {auditProspective,inputQuality} from '../site/nfl-quality.mjs';
test('empty prospective grading must not imply promotion',()=>{
 const x=auditProspective({unique_games_graded:0,by_parameters:{}});
 assert.equal(x.approved,false);assert.equal(x.gradedGames,0);assert.deepEqual(x.rows,[]);
});
test('positive skill score alone cannot promote model',()=>{
 const key='a'.repeat(64)+'|'+'b'.repeat(64);
 const x=auditProspective({unique_games_graded:250,by_parameters:{[key]:{
 game_log_loss:{paired_games:250,challenger_minus_baseline:-0.01,paired_game_bootstrap_95pct:[-.04,-.001]},
 game_brier:{paired_games:250,challenger_minus_baseline:.001,paired_game_bootstrap_95pct:[-.02,.02]}
 }}});
 assert.equal(x.rows[0].significant,false);assert.equal(x.approved,false);
});
test('even statistical improvement only requests manual review',()=>{
 const key='a'.repeat(64)+'|'+'b'.repeat(64);
 const x=auditProspective({unique_games_graded:250,by_parameters:{[key]:{
 team_log_loss:{paired_games:250,challenger_minus_baseline:-.04,paired_game_bootstrap_95pct:[-.08,-.01]},
 team_brier:{paired_games:250,challenger_minus_baseline:-.02,paired_game_bootstrap_95pct:[-.04,-.005]}
 }}});
 assert.equal(x.rows[0].significant,true);assert.equal(x.approved,false);
});
test('missing injury and participation evidence fails input quality checks',()=>{
 assert.equal(inputQuality().label,'Insufficient verification');
 assert.equal(inputQuality({rosterVerified:true,participationVerified:true}).verified,2);
});
